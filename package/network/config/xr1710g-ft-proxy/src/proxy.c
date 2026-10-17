// SPDX-License-Identifier: GPL-2.0-only
/* Advertise only this owned FT endpoint through the authenticated Mesh.
 * Experimental local EtherType: no FT/OUI dispatch, keys, IP or receive API.
 * The normal Mesh RX path learns Ethernet source -> transmitting Mesh node.
 */
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <linux/if_packet.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>

static const unsigned char bss[2][6] = {
 {0,0x58,0x28,0xd7,0x85,0x0b}, {0,0x58,0x28,0xd7,0x49,0xf4}
};
static const unsigned char bridge[2][6] = {
 {0,0x58,0x28,0xd7,0x85,0x08}, {0,0x58,0x28,0xd7,0x49,0xf1}
};

static int interface(int fd, const char *name, const unsigned char *mac)
{
 struct ifreq req = {0};
 if (!*name || strlen(name) >= IFNAMSIZ) return -1;
 memcpy(req.ifr_name, name, strlen(name));
 if (ioctl(fd, SIOCGIFHWADDR, &req) || memcmp(req.ifr_hwaddr.sa_data, mac, 6)) return -1;
 if (ioctl(fd, SIOCGIFFLAGS, &req) || !(req.ifr_flags & IFF_UP)) return -1;
 if (ioctl(fd, SIOCGIFINDEX, &req)) return -1;
 return req.ifr_ifindex;
}

int main(int argc, char **argv)
{
 unsigned char frame[60] = {0};
 struct sockaddr_ll dst = {0};
 int role, fd, idx;
 if (argc != 3 || (strcmp(argv[1], "ap1") && strcmp(argv[1], "ap2"))) return 2;
 role = !strcmp(argv[1], "ap2");
 fd = socket(AF_PACKET, SOCK_RAW | SOCK_CLOEXEC, htons(0x88b5));
 if (fd < 0) return 3;
 idx = interface(fd, "br-lan.1", bridge[role]);
 if (idx < 0 || interface(fd, argv[2], bss[role]) < 0) { close(fd); return 4; }
 memcpy(frame, bridge[1-role], 6);
 memcpy(frame+6, bss[role], 6);
 frame[12] = 0x88; frame[13] = 0xb5;
 memcpy(frame+14, "XR1710G-FT-PROXY", 16);
 frame[30] = 1; /* Advertisement format version, no receiver state. */
 dst.sll_family = AF_PACKET; dst.sll_protocol = htons(0x88b5);
 dst.sll_ifindex = idx; dst.sll_halen = 6;
 memcpy(dst.sll_addr, bridge[1-role], 6);
 ssize_t sent = sendto(fd, frame, sizeof(frame), MSG_DONTWAIT,
                      (struct sockaddr *)&dst, sizeof(dst));
 close(fd);
 return sent == (ssize_t)sizeof(frame) ? 0 : 5;
}
