// SPDX-License-Identifier: GPL-2.0-only
/*
 * xr-ppe-l2: client of the airoha "xr_ppe_l2" generic netlink owner of PPE
 * bridge templates.
 *
 *   xr-ppe-l2 state
 *   xr-ppe-l2 publish COOKIE IN OUT VID TAGGED SRC DST GENERATION
 *   xr-ppe-l2 revoke COOKIE
 *   xr-ppe-l2 collect [RETRIES]          coherent snapshot (JSON)
 *   xr-ppe-l2 reconcile FILE [ROUNDS]    lines: IN OUT VID TAGGED SRC DST
 *   xr-ppe-l2 trial-arm SECONDS          one kernel-timed L2 bind window per boot
 *   xr-ppe-l2 trial-stop                 end it now (revoke + clear bound FOE)
 *
 * collect is coherent only if the generation is identical before, inside
 * and after the dump, the owner set count agrees and the kernel did not mark
 * the dump interrupted. reconcile publishes only against such a snapshot and
 * restarts on a stale generation; it never forces the kernel to admit a
 * template. Output is one JSON object per invocation.
 */
#include <errno.h>
#include <linux/genetlink.h>
#include <linux/netlink.h>
#include <net/if.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#ifndef NETLINK_EXT_ACK
#define NETLINK_EXT_ACK 11
#endif

enum {
	CMD_UNSPEC, CMD_GET_STATE, CMD_PUBLISH, CMD_REVOKE, CMD_DUMP, CMD_TRIAL_ARM, CMD_TRIAL_STOP, CMD_CLASSIFY_ARM, CMD_NATIVE_ARM,
};

enum {
	A_UNSPEC, A_PAD, A_GENERATION, A_WRITERS, A_NF_LATCHED, A_NETDEV_LATCHED,
	A_BIND_ENABLED, A_BRIDGE_BIND_ENABLED, A_ENTRIES, A_COOKIE, A_IN_IFINDEX,
	A_OUT_IFINDEX, A_VID, A_IN_TAGGED, A_SRC, A_DST, A_PUB_GENERATION,
	A_CACHED, A_SUBFLOWS, A_EGRESS_TAGGED, A_TRIAL_SECONDS, A_TRIAL_STATE,
	A_TRIAL_REMAINING_MS, A_TRIAL_INVALIDATED, A_DSFIELD_PRESERVED, A_CLASSIFY_ONLY, A_NATIVE_PROBE, A_MAX_PLUS_ONE,
};
#define A_MAX (A_MAX_PLUS_ONE - 1)
#define MAX_ENTRIES 1024

struct state {
	uint64_t generation;
	uint32_t writers, entries, trial_remaining_ms, trial_invalidated;
	int nf_latched, netdev_latched, bind, bridge_bind, trial_state, dsfield_preserved, classify_only, native_probe;
};

struct entry {
	uint64_t cookie, generation, pub_generation;
	uint32_t in_ifindex, subflows;
	uint16_t vid;
	int in_tagged, cached, egress_tagged;
	uint8_t src[6], dst[6];
};

struct reply {
	int error;			/* negative errno from the kernel */
	char message[256];		/* extack text */
	struct state state;
	int has_state;
	uint64_t cookie;
};

static int sock_fd = -1;
static uint16_t family_id;
static uint32_t seqno = 1;

struct msgbuf {
	char data[1024];
	size_t len;
};

static struct nlattr *put_attr(struct msgbuf *m, uint16_t type, const void *v, size_t n)
{
	struct nlattr *a = (struct nlattr *)(m->data + m->len);

	a->nla_type = type;
	a->nla_len = NLA_HDRLEN + n;
	memcpy((char *)a + NLA_HDRLEN, v, n);
	m->len += NLA_ALIGN(a->nla_len);
	return a;
}

static void begin(struct msgbuf *m, uint16_t type, uint16_t flags, uint8_t cmd)
{
	struct nlmsghdr *h = (struct nlmsghdr *)m->data;
	struct genlmsghdr *g;

	memset(m, 0, sizeof(*m));
	h->nlmsg_type = type;
	h->nlmsg_flags = NLM_F_REQUEST | flags;
	h->nlmsg_seq = seqno++;
	g = (struct genlmsghdr *)NLMSG_DATA(h);
	g->cmd = cmd;
	g->version = 1;
	m->len = NLMSG_HDRLEN + GENL_HDRLEN;
}

static int send_msg(struct msgbuf *m)
{
	struct nlmsghdr *h = (struct nlmsghdr *)m->data;

	h->nlmsg_len = m->len;
	return send(sock_fd, m->data, m->len, 0) == (ssize_t)m->len ? 0 : -errno;
}

static void parse_attrs(struct nlattr **tb, int max, void *p, int len)
{
	struct nlattr *a;

	memset(tb, 0, sizeof(*tb) * (max + 1));
	for (a = p; len >= NLA_HDRLEN && a->nla_len >= NLA_HDRLEN && a->nla_len <= len;
	     len -= NLA_ALIGN(a->nla_len), a = (struct nlattr *)((char *)a + NLA_ALIGN(a->nla_len)))
		if ((a->nla_type & NLA_TYPE_MASK) <= max)
			tb[a->nla_type & NLA_TYPE_MASK] = a;
}

#define ADATA(a) ((void *)((char *)(a) + NLA_HDRLEN))
static uint64_t get_u64(struct nlattr *a) { uint64_t v = 0; if (a) memcpy(&v, ADATA(a), 8); return v; }
static uint32_t get_u32(struct nlattr *a) { uint32_t v = 0; if (a) memcpy(&v, ADATA(a), 4); return v; }
static uint16_t get_u16(struct nlattr *a) { uint16_t v = 0; if (a) memcpy(&v, ADATA(a), 2); return v; }
static int get_u8(struct nlattr *a) { return a ? *(uint8_t *)ADATA(a) : 0; }

static void parse_state(struct nlattr **tb, struct state *s)
{
	s->generation = get_u64(tb[A_GENERATION]);
	s->writers = get_u32(tb[A_WRITERS]);
	s->nf_latched = get_u8(tb[A_NF_LATCHED]);
	s->netdev_latched = get_u8(tb[A_NETDEV_LATCHED]);
	s->bind = get_u8(tb[A_BIND_ENABLED]);
	s->bridge_bind = get_u8(tb[A_BRIDGE_BIND_ENABLED]);
	s->entries = get_u32(tb[A_ENTRIES]);
	s->trial_state = get_u8(tb[A_TRIAL_STATE]);
	s->trial_remaining_ms = get_u32(tb[A_TRIAL_REMAINING_MS]);
	s->trial_invalidated = get_u32(tb[A_TRIAL_INVALIDATED]);
	/* Old kernels omit this capability; absence never grants offload. */
	s->dsfield_preserved = get_u8(tb[A_DSFIELD_PRESERVED]);
	s->classify_only = get_u8(tb[A_CLASSIFY_ONLY]);
	s->native_probe = get_u8(tb[A_NATIVE_PROBE]);
}

static void parse_error(struct nlmsghdr *h, struct reply *r)
{
	struct nlmsgerr *e = NLMSG_DATA(h);
	struct nlattr *tb[NLMSGERR_ATTR_MAX + 1];
	size_t off = sizeof(*e);

	r->error = e->error;
	if (!(h->nlmsg_flags & NLM_F_ACK_TLVS))
		return;
	if (!(h->nlmsg_flags & NLM_F_CAPPED))
		off += e->msg.nlmsg_len - NLMSG_HDRLEN;
	if (NLMSG_HDRLEN + off > h->nlmsg_len)
		return;
	parse_attrs(tb, NLMSGERR_ATTR_MAX, (char *)e + off, h->nlmsg_len - NLMSG_HDRLEN - off);
	if (tb[NLMSGERR_ATTR_MSG])
		snprintf(r->message, sizeof(r->message), "%s", (char *)ADATA(tb[NLMSGERR_ATTR_MSG]));
}

/* Receive the reply to a doit request: optional data message, then ACK. */
static int transact(struct msgbuf *m, struct reply *r)
{
	char buf[16384];
	uint32_t seq = ((struct nlmsghdr *)m->data)->nlmsg_seq;
	int err;

	memset(r, 0, sizeof(*r));
	((struct nlmsghdr *)m->data)->nlmsg_flags |= NLM_F_ACK;
	err = send_msg(m);
	if (err)
		return err;
	for (;;) {
		ssize_t n = recv(sock_fd, buf, sizeof(buf), 0);
		struct nlmsghdr *h;

		if (n < 0)
			return -errno;
		for (h = (struct nlmsghdr *)buf; NLMSG_OK(h, (size_t)n); h = NLMSG_NEXT(h, n)) {
			if (h->nlmsg_seq != seq)
				continue;
			if (h->nlmsg_type == NLMSG_ERROR) {
				parse_error(h, r);
				return 0;
			}
			if (h->nlmsg_type == family_id || h->nlmsg_type == GENL_ID_CTRL) {
				struct nlattr *tb[A_MAX + 1];

				if (h->nlmsg_type == GENL_ID_CTRL) {
					struct nlattr *ct[CTRL_ATTR_MAX + 1];

					parse_attrs(ct, CTRL_ATTR_MAX, (char *)NLMSG_DATA(h) + GENL_HDRLEN,
						    h->nlmsg_len - NLMSG_HDRLEN - GENL_HDRLEN);
					if (ct[CTRL_ATTR_FAMILY_ID])
						family_id = get_u16(ct[CTRL_ATTR_FAMILY_ID]);
					continue;
				}
				parse_attrs(tb, A_MAX, (char *)NLMSG_DATA(h) + GENL_HDRLEN,
					    h->nlmsg_len - NLMSG_HDRLEN - GENL_HDRLEN);
				parse_state(tb, &r->state);
				r->has_state = 1;
				r->cookie = get_u64(tb[A_COOKIE]);
			}
		}
	}
}

static int open_family(void)
{
	struct msgbuf m;
	struct reply r;
	int one = 1;

	sock_fd = socket(AF_NETLINK, SOCK_RAW | SOCK_CLOEXEC, NETLINK_GENERIC);
	if (sock_fd < 0)
		return -errno;
	setsockopt(sock_fd, SOL_NETLINK, NETLINK_EXT_ACK, &one, sizeof(one));
	begin(&m, GENL_ID_CTRL, 0, CTRL_CMD_GETFAMILY);
	((struct genlmsghdr *)NLMSG_DATA((struct nlmsghdr *)m.data))->version = 2;
	put_attr(&m, CTRL_ATTR_FAMILY_NAME, "xr_ppe_l2", sizeof("xr_ppe_l2"));
	if (transact(&m, &r))
		return -EIO;
	return family_id ? 0 : (r.error ? r.error : -ENOENT);
}

static int get_state(struct state *s, struct reply *r)
{
	struct msgbuf m;
	int err;

	begin(&m, family_id, 0, CMD_GET_STATE);
	err = transact(&m, r);
	if (err)
		return err;
	if (r->error)
		return r->error;
	*s = r->state;
	return r->has_state ? 0 : -EPROTO;
}

/* One dump; *intr set if any part carried NLM_F_DUMP_INTR. */
static int dump(struct entry *out, int *count, int *intr)
{
	char buf[32768];
	struct msgbuf m;
	uint32_t seq;
	int err;

	*count = 0;
	*intr = 0;
	begin(&m, family_id, NLM_F_DUMP, CMD_DUMP);
	seq = ((struct nlmsghdr *)m.data)->nlmsg_seq;
	err = send_msg(&m);
	if (err)
		return err;
	for (;;) {
		ssize_t n = recv(sock_fd, buf, sizeof(buf), 0);
		struct nlmsghdr *h;

		if (n < 0)
			return -errno;
		for (h = (struct nlmsghdr *)buf; NLMSG_OK(h, (size_t)n); h = NLMSG_NEXT(h, n)) {
			struct nlattr *tb[A_MAX + 1];
			struct entry *e;

			if (h->nlmsg_seq != seq)
				continue;
			if (h->nlmsg_flags & NLM_F_DUMP_INTR)
				*intr = 1;
			if (h->nlmsg_type == NLMSG_DONE)
				return 0;
			if (h->nlmsg_type == NLMSG_ERROR)
				return ((struct nlmsgerr *)NLMSG_DATA(h))->error;
			if (h->nlmsg_type != family_id || *count >= MAX_ENTRIES)
				continue;
			parse_attrs(tb, A_MAX, (char *)NLMSG_DATA(h) + GENL_HDRLEN,
				    h->nlmsg_len - NLMSG_HDRLEN - GENL_HDRLEN);
			e = &out[(*count)++];
			memset(e, 0, sizeof(*e));
			e->cookie = get_u64(tb[A_COOKIE]);
			e->generation = get_u64(tb[A_GENERATION]);
			e->pub_generation = get_u64(tb[A_PUB_GENERATION]);
			e->in_ifindex = get_u32(tb[A_IN_IFINDEX]);
			e->vid = get_u16(tb[A_VID]);
			e->in_tagged = get_u8(tb[A_IN_TAGGED]);
			e->cached = get_u8(tb[A_CACHED]);
			e->subflows = get_u32(tb[A_SUBFLOWS]);
			e->egress_tagged = get_u8(tb[A_EGRESS_TAGGED]);
			if (tb[A_SRC])
				memcpy(e->src, ADATA(tb[A_SRC]), 6);
			if (tb[A_DST])
				memcpy(e->dst, ADATA(tb[A_DST]), 6);
		}
	}
}

struct snapshot {
	struct state state;
	struct entry entries[MAX_ENTRIES];
	int count, attempts, coherent, interrupted;
};

static int collect(struct snapshot *s, int retries)
{
	s->interrupted = 0;
	for (s->attempts = 1; s->attempts <= retries; s->attempts++) {
		struct state before, after;
		struct reply r;
		int i, intr, err;

		err = get_state(&before, &r);
		if (!err)
			err = dump(s->entries, &s->count, &intr);
		if (!err)
			err = get_state(&after, &r);
		if (err)
			return err;
		s->interrupted += intr;
		s->coherent = !intr && before.generation == after.generation &&
			      before.entries == after.entries &&
			      (uint32_t)s->count == before.entries;
		for (i = 0; s->coherent && i < s->count; i++)
			if (s->entries[i].generation != before.generation)
				s->coherent = 0;
		s->state = after;
		if (s->coherent)
			return 0;
	}
	s->attempts = retries;	/* incoherent after every attempt */
	return 0;
}

static void print_state_fields(const struct state *s)
{
	printf("\"generation\":%llu,\"writers\":%u,\"nf_latched\":%d,\"netdev_latched\":%d,"
	       "\"bind\":%d,\"bridge_bind\":%d,\"entries\":%u,\"trial_state\":%d,"
	       "\"trial_remaining_ms\":%u,\"trial_invalidated\":%u,\"dsfield_preserved\":%d,\"classify_only\":%d,\"native_probe\":%d",
	       (unsigned long long)s->generation, s->writers, s->nf_latched, s->netdev_latched,
	       s->bind, s->bridge_bind, s->entries, s->trial_state, s->trial_remaining_ms,
	       s->trial_invalidated, s->dsfield_preserved, s->classify_only, s->native_probe);
}

static void print_mac(const char *name, const uint8_t *m)
{
	printf("\"%s\":\"%02x:%02x:%02x:%02x:%02x:%02x\"", name, m[0], m[1], m[2], m[3], m[4], m[5]);
}

static void print_json_string(const char *s)
{
	putchar('"');
	for (; *s; s++) {
		if (*s == '"' || *s == '\\')
			putchar('\\');
		if ((unsigned char)*s >= 0x20)
			putchar(*s);
	}
	putchar('"');
}

static void print_error(int err, const char *msg)
{
	printf("{\"ok\":false,\"errno\":%d,\"error\":", -err);
	print_json_string(strerror(-err));
	printf(",\"message\":");
	print_json_string(msg ? msg : "");
	printf("}\n");
}

static int parse_mac(const char *s, uint8_t *m)
{
	unsigned int v[6];
	int i;

	if (sscanf(s, "%x:%x:%x:%x:%x:%x", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) != 6)
		return -1;
	for (i = 0; i < 6; i++) {
		if (v[i] > 255)
			return -1;
		m[i] = v[i];
	}
	return 0;
}

static uint32_t parse_ifindex(const char *s)
{
	char *end;
	unsigned long v = strtoul(s, &end, 10);

	return *end ? if_nametoindex(s) : (uint32_t)v;
}

struct request {
	uint64_t cookie;
	uint32_t in, out;
	uint16_t vid;
	uint8_t tagged, src[6], dst[6];
};

static int publish_template(const struct request *q, uint64_t generation, struct reply *r)
{
	struct msgbuf m;
	int err;

	begin(&m, family_id, 0, CMD_PUBLISH);
	put_attr(&m, A_COOKIE, &q->cookie, 8);
	put_attr(&m, A_GENERATION, &generation, 8);
	put_attr(&m, A_IN_IFINDEX, &q->in, 4);
	put_attr(&m, A_OUT_IFINDEX, &q->out, 4);
	put_attr(&m, A_VID, &q->vid, 2);
	put_attr(&m, A_IN_TAGGED, &q->tagged, 1);
	put_attr(&m, A_SRC, q->src, 6);
	put_attr(&m, A_DST, q->dst, 6);
	err = transact(&m, r);
	return err ? err : r->error;
}

static int revoke_template(uint64_t cookie, struct reply *r)
{
	struct msgbuf m;
	int err;

	begin(&m, family_id, 0, CMD_REVOKE);
	put_attr(&m, A_COOKIE, &cookie, 8);
	err = transact(&m, r);
	return err ? err : r->error;
}

/* Parse "IN OUT VID TAGGED SRC DST"; the cookie is a FNV-1a hash of the
 * normalized tuple, so the same desired template keeps the same owner id.
 */
static int parse_request(char **f, struct request *q)
{
	char norm[128];
	const unsigned char *p;
	uint64_t h = 1469598103934665603ULL;
	unsigned long vid, tagged;
	char *end;

	memset(q, 0, sizeof(*q));
	q->in = parse_ifindex(f[0]);
	q->out = parse_ifindex(f[1]);
	vid = strtoul(f[2], &end, 10);
	if (*end || vid > 4094)
		return -1;
	tagged = strtoul(f[3], &end, 10);
	if (*end || tagged > 1)
		return -1;
	if (!q->in || !q->out || parse_mac(f[4], q->src) || parse_mac(f[5], q->dst))
		return -1;
	q->vid = vid;
	q->tagged = tagged;
	snprintf(norm, sizeof(norm), "%u %u %u %u %02x%02x%02x%02x%02x%02x %02x%02x%02x%02x%02x%02x",
		 q->in, q->out, q->vid, q->tagged, q->src[0], q->src[1], q->src[2], q->src[3],
		 q->src[4], q->src[5], q->dst[0], q->dst[1], q->dst[2], q->dst[3], q->dst[4], q->dst[5]);
	for (p = (const unsigned char *)norm; *p; p++)
		h = (h ^ *p) * 1099511628211ULL;
	q->cookie = h ? h : 1;
	return 0;
}

static int cmd_reconcile(const char *file, int rounds)
{
	static struct snapshot s;
	struct request want[MAX_ENTRIES];
	int nwant = 0, round, published = 0, revoked = 0, failures = 0, i, j;
	char line[256], *f[8], *tok, *save;
	FILE *fp = fopen(file, "r");

	if (!fp) {
		print_error(-errno, file);
		return 1;
	}
	while (fgets(line, sizeof(line), fp) && nwant < MAX_ENTRIES) {
		int n = 0;

		if (line[0] == '#')
			continue;
		for (tok = strtok_r(line, " \t\r\n", &save); tok && n < 7; tok = strtok_r(NULL, " \t\r\n", &save))
			f[n++] = tok;
		if (!n)
			continue;
		if (n != 6 || parse_request(f, &want[nwant])) {
			print_error(-EINVAL, "malformed desired template line");
			fclose(fp);
			return 1;
		}
		nwant++;
	}
	fclose(fp);

	printf("{\"failures\":[");
	for (round = 1; round <= rounds; round++) {
		int restart = 0;

		if (collect(&s, 5) || !s.coherent) {
			restart = 1;
			continue;
		}
		/* Revoke owned entries that are not desired or no longer cached,
		 * then re-collect: the owner set changed.
		 */
		for (i = 0; i < s.count; i++) {
			int desired = 0;
			struct reply r;

			for (j = 0; j < nwant; j++)
				desired |= want[j].cookie == s.entries[i].cookie;
			if (desired && s.entries[i].cached)
				continue;
			if (!revoke_template(s.entries[i].cookie, &r))
				revoked++;
			restart = 1;
		}
		if (restart)
			continue;
		for (j = 0; j < nwant; j++) {
			struct reply r;
			int present = 0, err;

			for (i = 0; i < s.count; i++)
				present |= s.entries[i].cookie == want[j].cookie;
			if (present)
				continue;
			err = publish_template(&want[j], s.state.generation, &r);
			if (!err) {
				published++;
				s.state.generation = r.state.generation;
				continue;
			}
			if (err == -ESTALE || err == -EAGAIN || err == -EBUSY) {
				restart = 1;
				break;
			}
			/* Context rejections are reported once and not retried. */
			printf("%s{\"line\":%d,\"errno\":%d,\"message\":", failures ? "," : "", j + 1, -err);
			print_json_string(r.message);
			printf("}");
			failures++;
			want[j].cookie = 0;
		}
		if (!restart)
			break;
	}
	printf("],\"published\":%d,\"revoked\":%d,\"rounds\":%d,\"settled\":%s}\n",
	       published, revoked, round > rounds ? rounds : round, round <= rounds ? "true" : "false");
	return round <= rounds ? 0 : 3;
}

static int cmd_collect(int retries)
{
	static struct snapshot s;
	char name[IF_NAMESIZE];
	int i, err = collect(&s, retries);

	if (err) {
		print_error(err, "collect failed");
		return 1;
	}
	printf("{\"coherent\":%s,\"attempts\":%d,\"interrupted_dumps\":%d,",
	       s.coherent ? "true" : "false", s.attempts, s.interrupted);
	print_state_fields(&s.state);
	printf(",\"templates\":[");
	for (i = 0; i < s.count; i++) {
		const struct entry *e = &s.entries[i];

		printf("%s{\"cookie\":\"%016llx\",\"generation\":%llu,\"pub_generation\":%llu,"
		       "\"in_ifindex\":%u,\"in_ifname\":", i ? "," : "",
		       (unsigned long long)e->cookie, (unsigned long long)e->generation,
		       (unsigned long long)e->pub_generation, e->in_ifindex);
		print_json_string(if_indextoname(e->in_ifindex, name) ? name : "");
		printf(",\"vid\":%u,\"in_tagged\":%d,", e->vid, e->in_tagged);
		print_mac("src", e->src);
		putchar(',');
		print_mac("dst", e->dst);
		printf(",\"cached\":%d,\"subflows\":%u,\"egress_tagged\":%d}", e->cached, e->subflows,
		       e->egress_tagged);
	}
	printf("]}\n");
	return s.coherent ? 0 : 3;
}

int main(int argc, char **argv)
{
	struct reply r;
	struct state s;
	int err;

	if (argc < 2)
		goto usage;
	err = open_family();
	if (err) {
		print_error(err, "xr_ppe_l2 generic netlink family unavailable");
		return 1;
	}
	if (!strcmp(argv[1], "state") && argc == 2) {
		err = get_state(&s, &r);
		if (err) {
			print_error(err, r.message);
			return 1;
		}
		printf("{\"ok\":true,");
		print_state_fields(&s);
		printf("}\n");
		return 0;
	}
	if (!strcmp(argv[1], "publish") && argc == 10) {
		struct request q;
		char *end;
		unsigned long long gen;

		if (parse_request(argv + 3, &q))
			goto usage;
		q.cookie = strtoull(argv[2], &end, 0);
		if (*end)
			goto usage;
		gen = strtoull(argv[9], &end, 10);
		if (*end)
			goto usage;
		err = publish_template(&q, gen, &r);
		if (err) {
			print_error(err, r.message);
			return 1;
		}
		printf("{\"ok\":true,\"cookie\":\"%016llx\",", (unsigned long long)r.cookie);
		print_state_fields(&r.state);
		printf("}\n");
		return 0;
	}
	if (!strcmp(argv[1], "revoke") && argc == 3) {
		char *end;
		uint64_t cookie = strtoull(argv[2], &end, 0);

		if (*end)
			goto usage;
		err = revoke_template(cookie, &r);
		if (err) {
			print_error(err, r.message);
			return 1;
		}
		printf("{\"ok\":true,");
		print_state_fields(&r.state);
		printf("}\n");
		return 0;
	}
	if (((!strcmp(argv[1], "trial-arm") || !strcmp(argv[1], "classify-arm") || !strcmp(argv[1], "native-arm")) && argc == 3) ||
	    (!strcmp(argv[1], "trial-stop") && argc == 2)) {
		struct msgbuf m;
		uint32_t seconds;
		char *end;

		begin(&m, family_id, 0, argc == 3 ? (!strcmp(argv[1], "classify-arm") ? CMD_CLASSIFY_ARM : !strcmp(argv[1], "native-arm") ? CMD_NATIVE_ARM : CMD_TRIAL_ARM) : CMD_TRIAL_STOP);
		if (argc == 3) {
			seconds = strtoul(argv[2], &end, 10);
			if (*end)
				goto usage;
			put_attr(&m, A_TRIAL_SECONDS, &seconds, 4);
		}
		err = transact(&m, &r);
		if (!err)
			err = r.error;
		if (err) {
			print_error(err, r.message);
			return 1;
		}
		printf("{\"ok\":true,");
		print_state_fields(&r.state);
		printf("}\n");
		return 0;
	}
	if (!strcmp(argv[1], "collect") && argc <= 3)
		return cmd_collect(argc == 3 ? atoi(argv[2]) : 5);
	if (!strcmp(argv[1], "reconcile") && (argc == 3 || argc == 4))
		return cmd_reconcile(argv[2], argc == 4 ? atoi(argv[3]) : 5);
usage:
	fprintf(stderr, "usage: xr-ppe-l2 state | publish COOKIE IN OUT VID TAGGED SRC DST GENERATION |\n"
		"       revoke COOKIE | collect [RETRIES] | reconcile FILE [ROUNDS] |\n"
		"       trial-arm SECONDS | classify-arm SECONDS | native-arm SECONDS | trial-stop\n");
	return 2;
}
