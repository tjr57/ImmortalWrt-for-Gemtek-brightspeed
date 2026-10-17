// SPDX-License-Identifier: GPL-2.0-only
/*
 * xr-mem-integrity - bounded userspace memory-integrity pattern tester.
 *
 * Why this exists: two independent kernel IABT faults on this target
 * (2026-10-11 AP44 modprobe/vfs_open, 2026-10-12 AP47 napi/dequeue_entities)
 * both read back a frame-record saved-LR slot whose value was the correct
 * return address with exactly bit63 cleared, while the saved fp loaded by the
 * same ldp was correct. This tool is a filter for that signature: it reports
 * whether 64-bit words read back with individual bits wrong, which bit
 * indices differ, whether the corruption is persistent (the stored value is
 * wrong) or transient (an immediate re-read returns the expected value), and
 * the physical address when pagemap exposes it.
 *
 * Scope limits, which must be quoted whenever a result is interpreted:
 *   - covers only this process's anonymous pages;
 *   - does NOT cover vmapped kernel stack pages, kernel data structures, or
 *     DMA-coherent/ring buffers;
 *   - a negative result weakens but does not exclude a memory-subsystem or
 *     load-path mechanism, and cannot exclude a fault that only manifests in
 *     a specific instruction window;
 *   - this is a diagnostic filter, not a repair and not an acceptance test.
 *
 * No network access, no device access, no configuration writes. The only file
 * written is the bounded JSON result named by --out.
 *
 * Exit status: 0 completed with a written result, 1 fatal or selftest failure,
 * 2 bad usage, 3 stopped on deadline/signal (partial coverage, not a pass).
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/utsname.h>

#define MAX_RECORDS 256u
#define CHECK_CLOCK_EVERY 8192u

enum pattern {
	PAT_WALK_ONE = 0,
	PAT_WALK_ZERO,
	PAT_ZERO,
	PAT_ONES,
	PAT_ALT_BYTE,
	PAT_ADDR,
	PAT_PRNG,
	PAT_COUNT
};

static const char *const pattern_name[PAT_COUNT] = {
	"walk-one", "walk-zero", "zero", "ones", "alt-byte", "addr", "prng"
};

struct record {
	uint64_t offset;
	uint64_t vaddr;
	uint64_t paddr;
	uint64_t expected;
	uint64_t actual;
	uint64_t xr;
	uint64_t reread1;
	uint64_t reread2;
	uint64_t monotonic_ns;
	int pass;
	int pattern;
	int sub;
	int classification; /* 0 persistent, 1 transient, 2 ambiguous */
	int bit_count;
	int bits[64];
};

struct config {
	uint64_t size;
	uint64_t seconds;
	int passes;
	int pin_cpu;
	int use_ldp;
	int retention_seconds;
	int selftest;
	int patterns[PAT_COUNT];
	int pattern_count;
	const char *out;
};

struct counters {
	uint64_t words_filled;
	uint64_t words_checked;
	uint64_t passes_done;
	uint64_t mismatches;
	uint64_t records_dropped;
	uint64_t transient_n;
	uint64_t persistent_n;
	uint64_t ambiguous_n;
	uint64_t ldp_pairs_checked;
	uint64_t bit_hist[64];
};

static struct record records[MAX_RECORDS];
static unsigned record_count;
static struct counters cnt;
static struct config cfg;
static long page_size;
static int pagemap_fd = -1;
static int pagemap_pfn_available;
static uint64_t deadline_ns;
static uint64_t buffer_paddr_first;
static volatile sig_atomic_t stop_requested;

#if defined(__aarch64__)
#define XR_HAVE_LDP 1
/* Same instruction class as the epilogue "ldp x29, x30, [sp], #N" whose x30
 * came back with bit63 cleared in both recorded faults. */
static inline void xr_ldp(const void *p, uint64_t *a, uint64_t *b)
{
	__asm__ volatile("ldp %0, %1, [%2]"
			 : "=r"(*a), "=r"(*b)
			 : "r"(p)
			 : "memory");
}
#endif

static uint64_t now_ns(void)
{
	struct timespec ts;

	if (clock_gettime(CLOCK_MONOTONIC, &ts))
		return 0;
	return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void on_stop(int sig)
{
	(void)sig;
	stop_requested = 1;
}

static uint64_t splitmix64(uint64_t x)
{
	x += 0x9e3779b97f4a7c15ull;
	x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ull;
	x = (x ^ (x >> 27)) * 0x94d049bb133111ebull;
	return x ^ (x >> 31);
}

static uint64_t pattern_value(int pat, int sub, uint64_t index, uint64_t vaddr)
{
	switch (pat) {
	case PAT_WALK_ONE:
		return 1ull << (sub & 63);
	case PAT_WALK_ZERO:
		return ~(1ull << (sub & 63));
	case PAT_ZERO:
		return 0;
	case PAT_ONES:
		return ~0ull;
	case PAT_ALT_BYTE:
		return (sub & 1) ? 0xff00ff00ff00ff00ull : 0x00ff00ff00ff00ffull;
	case PAT_ADDR:
		return vaddr ^ splitmix64(index);
	case PAT_PRNG:
		return splitmix64(splitmix64(index) ^ 0x5deece66dull);
	default:
		return 0;
	}
}

static uint64_t phys_of(const void *v)
{
	uint64_t entry, pfn, off;

	if (pagemap_fd < 0 || !v)
		return 0;
	off = ((uint64_t)(uintptr_t)v / (uint64_t)page_size) * 8u;
	if (pread(pagemap_fd, &entry, sizeof(entry), (off_t)off) !=
	    (ssize_t)sizeof(entry))
		return 0;
	if (!(entry & (1ull << 63)))
		return 0;
	pfn = entry & ((1ull << 55) - 1);
	if (!pfn)
		return 0;
	pagemap_pfn_available = 1;
	return pfn * (uint64_t)page_size +
	       ((uint64_t)(uintptr_t)v % (uint64_t)page_size);
}

/* classify() is kept free of I/O so the selftest can exercise it directly. */
static int classify(uint64_t expected, uint64_t actual, uint64_t r1, uint64_t r2)
{
	if (r1 == actual && r2 == actual)
		return 0; /* persistent: the stored value really is wrong */
	if (r1 == expected && r2 == expected)
		return 1; /* transient: both re-reads return the expected value */
	return 2;         /* ambiguous: the re-reads disagree */
}

static void note_bits(uint64_t xr, int *bits, int *n)
{
	int i, c = 0;

	for (i = 0; i < 64; i++) {
		if (xr & (1ull << i)) {
			cnt.bit_hist[i]++;
			if (c < 64)
				bits[c++] = i;
		}
	}
	*n = c;
}

static void record_mismatch(uint64_t *base, uint64_t index, uint64_t expected,
			    uint64_t actual, int pass, int pat, int sub)
{
	struct record *r;
	uint64_t r1, r2;

	cnt.mismatches++;
	r1 = base[index];
	r2 = base[index];
	if (record_count >= MAX_RECORDS) {
		cnt.records_dropped++;
		return;
	}
	r = &records[record_count++];
	memset(r, 0, sizeof(*r));
	r->offset = index * 8u;
	r->vaddr = (uint64_t)(uintptr_t)&base[index];
	r->paddr = phys_of(&base[index]);
	r->expected = expected;
	r->actual = actual;
	r->xr = expected ^ actual;
	r->reread1 = r1;
	r->reread2 = r2;
	r->monotonic_ns = now_ns();
	r->pass = pass;
	r->pattern = pat;
	r->sub = sub;
	r->classification = classify(expected, actual, r1, r2);
	note_bits(r->xr, r->bits, &r->bit_count);
	if (r->classification == 0)
		cnt.persistent_n++;
	else if (r->classification == 1)
		cnt.transient_n++;
	else
		cnt.ambiguous_n++;
}

static int expired(void)
{
	return deadline_ns && now_ns() >= deadline_ns;
}

static void fill(volatile uint64_t *buf, uint64_t words, int pat, int sub)
{
	uint64_t i;

	for (i = 0; i < words; i++) {
		buf[i] = pattern_value(pat, sub, i, (uint64_t)(uintptr_t)&buf[i]);
		if ((i & (CHECK_CLOCK_EVERY - 1)) == 0 && expired()) {
			stop_requested = 1;
			break;
		}
	}
	cnt.words_filled += i;
}

static void verify(uint64_t *buf, uint64_t words, int pat, int sub, int pass)
{
	uint64_t i = 0, n = 0, expected;
	unsigned checked = 0;

	while (i < words) {
		expected = pattern_value(pat, sub, i, (uint64_t)(uintptr_t)&buf[i]);
#ifdef XR_HAVE_LDP
		if (cfg.use_ldp && i + 1 < words) {
			uint64_t a, b;

			xr_ldp(&buf[i], &a, &b);
			cnt.ldp_pairs_checked++;
			if (a != expected)
				record_mismatch(buf, i, expected, a, pass, pat, sub);
			i++;
			n++;
			expected = pattern_value(pat, sub, i,
						 (uint64_t)(uintptr_t)&buf[i]);
			if (b != expected)
				record_mismatch(buf, i, expected, b, pass, pat, sub);
			i++;
			n++;
		} else
#endif
		{
			if (buf[i] != expected)
				record_mismatch(buf, i, expected, buf[i], pass,
						pat, sub);
			i++;
			n++;
		}
		if (++checked >= CHECK_CLOCK_EVERY) {
			checked = 0;
			if (expired())
				stop_requested = 1;
			if (stop_requested)
				break;
		}
	}
	cnt.words_checked += n;
}

static int sub_count(int pat)
{
	if (pat == PAT_WALK_ONE || pat == PAT_WALK_ZERO)
		return 64;
	if (pat == PAT_ALT_BYTE)
		return 2;
	return 1;
}

/* run_passes() returns non-zero only when every requested pass completed. */
static int run_passes(uint64_t *buf, uint64_t words)
{
	int pass, pi, sub;

	for (pass = 0; pass < cfg.passes && !stop_requested; pass++) {
		for (pi = 0; pi < cfg.pattern_count && !stop_requested; pi++) {
			int pat = cfg.patterns[pi];

			for (sub = 0; sub < sub_count(pat) && !stop_requested;
			     sub++) {
				fill(buf, words, pat, sub);
				if (cfg.retention_seconds > 0 &&
				    !stop_requested) {
					unsigned int remain =
						(unsigned int)cfg.retention_seconds;

					while (remain && !stop_requested)
						remain = sleep(remain);
				}
				if (stop_requested)
					break;
				verify(buf, words, pat, sub, pass);
				cnt.passes_done++;
			}
		}
	}
	return !stop_requested;
}

/* ---- selftest: prove detection, bit-index reporting and classification ---- */

struct selftest_case {
	const char *name;
	int passed;
	char detail[256];
};

static struct selftest_case selftests[8];
static unsigned selftest_count;

static void st_record(const char *name, int passed, const char *fmt, ...)
	__attribute__((format(printf, 3, 4)));

static void st_record(const char *name, int passed, const char *fmt, ...)
{
	struct selftest_case *c;
	va_list ap;

	if (selftest_count >= sizeof(selftests) / sizeof(selftests[0]))
		return;
	c = &selftests[selftest_count++];
	c->name = name;
	c->passed = passed;
	va_start(ap, fmt);
	vsnprintf(c->detail, sizeof(c->detail), fmt, ap);
	va_end(ap);
}

static int selftest(void)
{
	uint64_t words = 4096, i, expected;
	uint64_t *buf;
	unsigned target = 1234;
	int rc = 0;

	buf = mmap(NULL, words * 8u, PROT_READ | PROT_WRITE,
		   MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE, -1, 0);
	if (buf == MAP_FAILED) {
		st_record("allocate", 0, "mmap failed: %s", strerror(errno));
		return 1;
	}

	/* Case 1: the exact recorded signature - bit63 cleared on one word of a
	 * walk-one pattern whose every word already has bit63 set. */
	record_count = 0;
	memset(&cnt, 0, sizeof(cnt));
	fill(buf, words, PAT_WALK_ONE, 63);
	expected = pattern_value(PAT_WALK_ONE, 63, target,
				 (uint64_t)(uintptr_t)&buf[target]);
	buf[target] = expected & ~(1ull << 63);
	verify(buf, words, PAT_WALK_ONE, 63, 0);
	st_record("detect-bit63-clear",
		  record_count == 1 && cnt.mismatches == 1 &&
			  records[0].bits[0] == 63 && records[0].bit_count == 1 &&
			  records[0].classification == 0 &&
			  records[0].offset == target * 8u,
		  "mismatches=%" PRIu64 " recorded=%u first_bit=%d class=%d offset=%" PRIu64,
		  cnt.mismatches, record_count,
		  record_count ? records[0].bits[0] : -1,
		  record_count ? records[0].classification : -1,
		  record_count ? records[0].offset : 0);
	if (record_count != 1 || records[0].bits[0] != 63 ||
	    records[0].classification != 0)
		rc = 1;

	/* Case 2: classification logic for transient and ambiguous re-reads. */
	st_record("classify-persistent",
		  classify(0x8000000000000000ull, 0, 0, 0) == 0, "expected 0");
	st_record("classify-transient",
		  classify(0x8000000000000000ull, 0, 0x8000000000000000ull,
			   0x8000000000000000ull) == 1,
		  "expected 1");
	st_record("classify-ambiguous",
		  classify(0x8000000000000000ull, 0, 0x8000000000000000ull, 0) == 2,
		  "expected 2");

	/* Case 3: a restored buffer verifies clean, proving no sticky state. */
	buf[target] = expected;
	record_count = 0;
	memset(&cnt, 0, sizeof(cnt));
	verify(buf, words, PAT_WALK_ONE, 63, 0);
	st_record("clean-after-restore", cnt.mismatches == 0 && record_count == 0,
		  "mismatches=%" PRIu64, cnt.mismatches);
	if (cnt.mismatches)
		rc = 1;

	/* Case 4: an address-derived pattern catches a wrong-location write. */
	record_count = 0;
	memset(&cnt, 0, sizeof(cnt));
	fill(buf, words, PAT_ADDR, 0);
	for (i = 0; i + 1 < words; i += 512)
		buf[i] = buf[i + 1];
	verify(buf, words, PAT_ADDR, 0, 0);
	st_record("detect-addr-pattern-swap", cnt.mismatches == 8,
		  "mismatches=%" PRIu64 " expected 8", cnt.mismatches);
	if (cnt.mismatches != 8)
		rc = 1;

	/* Case 5: the paired ldp access path is exercised where available. */
#ifdef XR_HAVE_LDP
	{
		uint64_t a = 0;
		uint64_t b = 0;

		record_count = 0;
		memset(&cnt, 0, sizeof(cnt));
		fill(buf, words, PAT_WALK_ZERO, 63);
		buf[8] = pattern_value(PAT_WALK_ZERO, 63, 8,
				       (uint64_t)(uintptr_t)&buf[8]) | (1ull << 63);
		cfg.use_ldp = 1;
		xr_ldp(&buf[8], &a, &b);
		verify(buf, words, PAT_WALK_ZERO, 63, 0);
		cfg.use_ldp = 0;
		st_record("detect-via-ldp-pair",
			  cnt.ldp_pairs_checked == words / 2 &&
				  cnt.mismatches == 1 && record_count == 1 &&
				  records[0].bits[0] == 63 &&
				  records[0].offset == 8u * 8u,
			  "pairs=%" PRIu64 " expected=%" PRIu64
			  " mismatches=%" PRIu64 " a=%016" PRIx64,
			  cnt.ldp_pairs_checked, words / 2, cnt.mismatches, a);
		if (cnt.ldp_pairs_checked != words / 2 || cnt.mismatches != 1)
			rc = 1;
	}
#else
	st_record("detect-via-ldp-pair", 1, "not applicable on this host");
#endif

	munmap(buf, words * 8u);
	return rc;
}

/* ---- output ---- */

static void json_escape(FILE *f, const char *s)
{
	fputc('"', f);
	for (; *s; s++) {
		if (*s == '"' || *s == '\\')
			fputc('\\', f);
		fputc(*s, f);
	}
	fputc('"', f);
}

static int write_result(const char *path, uint64_t *buf, uint64_t words,
			int completed, int selftest_rc)
{
	struct utsname uts;
	FILE *f;
	unsigned i;
	int b;

	f = path ? fopen(path, "w") : stdout;
	if (!f) {
		fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
		return 1;
	}
	memset(&uts, 0, sizeof(uts));
	uname(&uts);
	fprintf(f, "{\n");
	fprintf(f, "  \"schema\": 1,\n");
	fprintf(f, "  \"tool\": \"xr-mem-integrity\",\n");
	fprintf(f, "  \"mode\": \"%s\",\n", selftest_rc >= 0 ? "selftest" : "run");
	fprintf(f, "  \"monotonicNs\": %" PRIu64 ",\n", now_ns());
	fprintf(f, "  \"kernelRelease\": ");
	json_escape(f, uts.release);
	fprintf(f, ",\n  \"machine\": ");
	json_escape(f, uts.machine);
	fprintf(f, ",\n");
	fprintf(f, "  \"pageSize\": %ld,\n", page_size);
	fprintf(f, "  \"pagemapPfnAvailable\": %s,\n",
		pagemap_pfn_available ? "true" : "false");
	fprintf(f, "  \"config\": {\n");
	fprintf(f, "    \"bytes\": %" PRIu64 ",\n", cfg.size);
	fprintf(f, "    \"words\": %" PRIu64 ",\n", words);
	fprintf(f, "    \"deadlineSeconds\": %" PRIu64 ",\n", cfg.seconds);
	fprintf(f, "    \"passes\": %d,\n", cfg.passes);
	fprintf(f, "    \"pinCpu\": %d,\n", cfg.pin_cpu);
	fprintf(f, "    \"useLdp\": %s,\n", cfg.use_ldp ? "true" : "false");
	fprintf(f, "    \"retentionSeconds\": %d,\n", cfg.retention_seconds);
	fprintf(f, "    \"patterns\": [");
	for (i = 0; i < (unsigned)cfg.pattern_count; i++)
		fprintf(f, "%s\"%s\"", i ? ", " : "",
			pattern_name[cfg.patterns[i]]);
	fprintf(f, "]\n  },\n");
	fprintf(f, "  \"completed\": %s,\n", completed ? "true" : "false");
	fprintf(f, "  \"stopRequested\": %s,\n",
		stop_requested ? "true" : "false");
	fprintf(f, "  \"counters\": {\n");
	fprintf(f, "    \"wordsFilled\": %" PRIu64 ",\n", cnt.words_filled);
	fprintf(f, "    \"wordsChecked\": %" PRIu64 ",\n", cnt.words_checked);
	fprintf(f, "    \"patternPassesDone\": %" PRIu64 ",\n", cnt.passes_done);
	fprintf(f, "    \"ldpPairsChecked\": %" PRIu64 ",\n", cnt.ldp_pairs_checked);
	fprintf(f, "    \"mismatches\": %" PRIu64 ",\n", cnt.mismatches);
	fprintf(f, "    \"recordsDropped\": %" PRIu64 ",\n", cnt.records_dropped);
	fprintf(f, "    \"persistent\": %" PRIu64 ",\n", cnt.persistent_n);
	fprintf(f, "    \"transient\": %" PRIu64 ",\n", cnt.transient_n);
	fprintf(f, "    \"ambiguous\": %" PRIu64 "\n", cnt.ambiguous_n);
	fprintf(f, "  },\n");
	fprintf(f, "  \"bitHistogram\": {");
	for (b = 0; b < 64; b++)
		fprintf(f, "%s\"%d\": %" PRIu64, b ? ", " : "", b, cnt.bit_hist[b]);
	fprintf(f, "},\n");
	fprintf(f, "  \"records\": [\n");
	for (i = 0; i < record_count; i++) {
		struct record *r = &records[i];
		int j;

		fprintf(f, "    {\"offset\": %" PRIu64 ", \"vaddr\": \"0x%" PRIx64
			   "\", \"paddr\": \"0x%" PRIx64 "\", \"expected\": \"0x%016"
			   PRIx64 "\", \"actual\": \"0x%016" PRIx64
			   "\", \"xor\": \"0x%016" PRIx64 "\", \"reread1\": \"0x%016"
			   PRIx64 "\", \"reread2\": \"0x%016" PRIx64
			   "\", \"pass\": %d, \"pattern\": \"%s\", \"sub\": %d, "
			   "\"classification\": %d, \"monotonicNs\": %" PRIu64
			   ", \"bits\": [",
			r->offset, r->vaddr, r->paddr, r->expected, r->actual,
			r->xr, r->reread1, r->reread2, r->pass,
			pattern_name[r->pattern], r->sub, r->classification,
			r->monotonic_ns);
		for (j = 0; j < r->bit_count; j++)
			fprintf(f, "%s%d", j ? ", " : "", r->bits[j]);
		fprintf(f, "]}%s\n", i + 1 < record_count ? "," : "");
	}
	fprintf(f, "  ],\n");
	if (selftest_count) {
		fprintf(f, "  \"selftest\": {\n    \"allPassed\": %s,\n    \"cases\": [\n",
			selftest_rc == 0 ? "true" : "false");
		for (i = 0; i < selftest_count; i++) {
			fprintf(f, "      {\"name\": ");
			json_escape(f, selftests[i].name);
			fprintf(f, ", \"passed\": %s, \"detail\": ",
				selftests[i].passed ? "true" : "false");
			json_escape(f, selftests[i].detail);
			fprintf(f, "}%s\n",
				i + 1 < selftest_count ? "," : "");
		}
		fprintf(f, "    ]\n  },\n");
	}
	fprintf(f, "  \"bufferVaddrRange\": [\"0x%" PRIx64 "\", \"0x%" PRIx64 "\"],\n",
		buf ? (uint64_t)(uintptr_t)buf : 0,
		buf ? (uint64_t)(uintptr_t)(buf + words) : 0);
	fprintf(f, "  \"bufferPaddrFirst\": \"0x%" PRIx64 "\",\n",
		buffer_paddr_first);
	fprintf(f, "  \"limits\": [\n");
	fprintf(f, "    \"Covers only this process's anonymous pages.\",\n");
	fprintf(f, "    \"Does not cover vmapped kernel stack pages, kernel data "
		   "or DMA-coherent buffers.\",\n");
	fprintf(f, "    \"A negative result weakens but does not exclude a "
		   "memory-subsystem or load-path mechanism.\",\n");
	fprintf(f, "    \"Diagnostic filter only: not a repair and not an "
		   "acceptance test.\"\n");
	fprintf(f, "  ]\n}\n");
	if (fflush(f)) {
		fprintf(stderr, "flush failed: %s\n", strerror(errno));
		if (path)
			fclose(f);
		return 1;
	}
	if (path)
		fclose(f);
	return 0;
}

static void usage(const char *argv0)
{
	fprintf(stderr,
		"usage: %s [--size BYTES] [--seconds N] [--passes N]\n"
		"          [--patterns all|zero,ones,walk-one,walk-zero,alt-byte,addr,prng]\n"
		"          [--pin CPU] [--ldp] [--retain SECONDS] [--out FILE]\n"
		"          [--selftest]\n",
		argv0);
}

static int parse_patterns(const char *spec)
{
	char buf[256];
	char *tok, *save = NULL;

	if (!strcmp(spec, "all")) {
		int i;

		cfg.pattern_count = 0;
		for (i = 0; i < PAT_COUNT; i++)
			cfg.patterns[cfg.pattern_count++] = i;
		return 0;
	}
	snprintf(buf, sizeof(buf), "%s", spec);
	cfg.pattern_count = 0;
	for (tok = strtok_r(buf, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
		int i, found = 0;

		for (i = 0; i < PAT_COUNT; i++) {
			if (!strcmp(tok, pattern_name[i])) {
				cfg.patterns[cfg.pattern_count++] = i;
				found = 1;
				break;
			}
		}
		if (!found) {
			fprintf(stderr, "unknown pattern: %s\n", tok);
			return 1;
		}
		if (cfg.pattern_count >= PAT_COUNT)
			break;
	}
	return cfg.pattern_count ? 0 : 1;
}

int main(int argc, char **argv)
{
	uint64_t *buf, words;
	int i, completed, selftest_rc = -1, rc;

	page_size = sysconf(_SC_PAGESIZE);
	if (page_size <= 0)
		page_size = 4096;
	cfg.size = 64ull << 20;
	cfg.seconds = 120;
	cfg.passes = 1;
	cfg.pin_cpu = -1;
	if (parse_patterns("zero,ones,walk-one,addr"))
		return 2;

	for (i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--size") && i + 1 < argc)
			cfg.size = strtoull(argv[++i], NULL, 0);
		else if (!strcmp(argv[i], "--seconds") && i + 1 < argc)
			cfg.seconds = strtoull(argv[++i], NULL, 0);
		else if (!strcmp(argv[i], "--passes") && i + 1 < argc)
			cfg.passes = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--pin") && i + 1 < argc)
			cfg.pin_cpu = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--retain") && i + 1 < argc)
			cfg.retention_seconds = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--patterns") && i + 1 < argc) {
			if (parse_patterns(argv[++i]))
				return 2;
		} else if (!strcmp(argv[i], "--ldp"))
			cfg.use_ldp = 1;
		else if (!strcmp(argv[i], "--out") && i + 1 < argc)
			cfg.out = argv[++i];
		else if (!strcmp(argv[i], "--selftest"))
			cfg.selftest = 1;
		else {
			usage(argv[0]);
			return 2;
		}
	}

	if (cfg.selftest) {
		selftest_rc = selftest();
		/* The top-level counters would otherwise show only the last
		 * selftest case, which is easy to misread as a run result. */
		memset(&cnt, 0, sizeof(cnt));
		record_count = 0;
		if (write_result(cfg.out, NULL, 0, 1, selftest_rc))
			return 1;
		return selftest_rc;
	}

	if (cfg.pin_cpu >= 0) {
		cpu_set_t set;

		CPU_ZERO(&set);
		CPU_SET(cfg.pin_cpu, &set);
		if (sched_setaffinity(0, sizeof(set), &set))
			fprintf(stderr, "warning: pin to cpu %d failed: %s\n",
				cfg.pin_cpu, strerror(errno));
	}

	buf = mmap(NULL, cfg.size, PROT_READ | PROT_WRITE,
		   MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE, -1, 0);
	if (buf == MAP_FAILED) {
		fprintf(stderr, "mmap %" PRIu64 " bytes failed: %s\n", cfg.size,
			strerror(errno));
		return 1;
	}
	if (mlock(buf, cfg.size))
		fprintf(stderr, "warning: mlock failed: %s\n", strerror(errno));
	pagemap_fd = open("/proc/self/pagemap", O_RDONLY | O_CLOEXEC);
	if (pagemap_fd < 0)
		fprintf(stderr, "warning: pagemap unavailable: %s\n",
			strerror(errno));

	/* Probe once up front. On a clean run nothing else calls phys_of(), so
	 * without this the availability flag would always be reported false
	 * even when physical addresses are in fact obtainable. */
	buffer_paddr_first = phys_of(buf);
	if (pagemap_fd >= 0 && !pagemap_pfn_available)
		fprintf(stderr, "warning: pagemap open but no PFN returned; "
				"physical addresses will be 0 (needs root)\n");

	words = cfg.size / 8u;
	signal(SIGTERM, on_stop);
	signal(SIGINT, on_stop);
	signal(SIGALRM, on_stop);
	if (cfg.seconds)
		alarm((unsigned int)cfg.seconds);
	deadline_ns = cfg.seconds ? now_ns() + cfg.seconds * 1000000000ull : 0;

	completed = run_passes(buf, words);

	rc = write_result(cfg.out, buf, words, completed, selftest_rc);
	if (pagemap_fd >= 0)
		close(pagemap_fd);
	munlock(buf, cfg.size);
	munmap(buf, cfg.size);
	if (!completed)
		return 3; /* deadline or signal: partial coverage, not a pass */
	return rc;
}
