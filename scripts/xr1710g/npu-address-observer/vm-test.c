// SPDX-License-Identifier: GPL-2.0-only
/* Disposable VM syscall checks; no hardware access. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define FILEPATH "/sys/kernel/debug/xr_npu_addresses/snapshot"
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr, "XR_ADDRESS_FAIL line=%d errno=%d\n", __LINE__, errno); return 1; } } while (0)

int main(int argc, char **argv)
{
	char buf[8192];
	struct stat st;
	int fd, status, expected;
	ssize_t n;
	pid_t child;

	REQUIRE(argc == 2);
	expected = atoi(argv[1]);
	fd = open(FILEPATH, O_RDONLY);
	REQUIRE(fd >= 0);
	REQUIRE(fstat(fd, &st) == 0 && (st.st_mode & 0777) == 0400);
	n = read(fd, buf, sizeof(buf) - 1);
	if (expected) {
		REQUIRE(n == -1 && errno == expected);
		REQUIRE(close(fd) == 0);
		printf("XR_EXPECTED_READ_ERROR=%d\n", expected);
		return 0;
	}
	REQUIRE(n > 0 && n < (ssize_t)sizeof(buf) - 1);
	buf[n] = 0;
	REQUIRE(strstr(buf, "schema=1 atomic=0 "));
	REQUIRE(strstr(buf, "cpu_rx0_dma_base offset=0x30d180 first=0x8030d180 second=0x8030d180 stable=1\n"));
	REQUIRE(strstr(buf, "wifi_txfree_ring_ptr offset=0x003964 first=0x80003964 second=0x80003964 stable=1\n"));
	puts(buf);
	REQUIRE(read(fd, buf, 1) == 0);
	REQUIRE(write(fd, "1", 1) == -1 && errno == EBADF);
	REQUIRE(syscall(SYS_delete_module, "xr_npu_addresses", O_NONBLOCK) == -1);
	REQUIRE(errno == EBUSY || errno == EWOULDBLOCK);
	REQUIRE(lseek(fd, 0, SEEK_SET) == 0);
	REQUIRE(read(fd, buf, sizeof(buf)) > 0);
	child = fork();
	REQUIRE(child >= 0);
	if (!child) {
		close(fd);
		if (setuid(65534)) _exit(2);
		int other = open(FILEPATH, O_RDONLY);
		_exit(other == -1 && errno == EACCES ? 0 : 3);
	}
	REQUIRE(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
	REQUIRE(close(fd) == 0);
	fd = open(FILEPATH, O_WRONLY);
	if (fd >= 0) {
		REQUIRE(write(fd, "1", 1) == -1);
		REQUIRE(close(fd) == 0);
	}
	puts("XR_PERMISSION_LIFETIME_REPEAT_PASS");
	return 0;
}
