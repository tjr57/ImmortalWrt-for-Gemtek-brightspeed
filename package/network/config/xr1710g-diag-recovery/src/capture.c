/* SPDX-License-Identifier: GPL-2.0-only
 * Bounded one-epoch /dev/kmsg retention. No network, NPU, reset or config writes.
 * A userspace logger cannot promise capture after hard lockup/power loss.
 */
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <limits.h>

#define RECORD_MAX 65536u
#define PRE_MAX 65536u
#define OUTPUT_MAX 262144u
#define RING_SLOTS 256u
struct record { char *text; size_t len; };
static struct record ring[RING_SLOTS];
static unsigned first, count;
static size_t ring_bytes, written;
static volatile sig_atomic_t stop;
static int dirfd=-1, logfile=-1;
static uint64_t last_seq, first_seq, records, gaps, fault_seq;
static int have_seq, fault, failed, capped;
static char boot[37];

static void stopped(int sig) { (void)sig; stop=1; }
static uint64_t now_ms(void) {
 struct timespec t;
 if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
 return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
}
static int write_all(int fd,const char *s,size_t n) {
 while(n) { ssize_t w=write(fd,s,n); if(w<0&&errno==EINTR)continue;
  if(w<=0)return -1;
  s+=w;n-=(size_t)w; }
 return 0;
}
static int file_once(const char *name,const char *data) {
 int fd=openat(dirfd,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;
 int result=write_all(fd,data,strlen(data));
 if(fsync(fd))result=-1;
 if(close(fd))result=-1;
 if(fsync(dirfd))result=-1;
 return result;
}
static int status(const char *name) {
 char s[768];
 int n=snprintf(s,sizeof(s),"{\"schema\":1,\"bootID\":\"%s\",\"pid\":%ld,\"records\":%"PRIu64",\"firstSeq\":%"PRIu64",\"lastSeq\":%"PRIu64",\"fault\":%s,\"faultSeq\":%"PRIu64",\"gaps\":%"PRIu64",\"failed\":%s,\"capped\":%s,\"written\":%zu,\"monotonicMs\":%"PRIu64"}\n",
  boot,(long)getpid(),records,first_seq,last_seq,fault?"true":"false",fault_seq,gaps,
  failed?"true":"false",capped?"true":"false",written,now_ms());
 if(n<0||(size_t)n>=sizeof(s))return -1;
 return file_once(name,s);
}
static int decimal(const char **s,uint64_t *v) {
 if(**s<'0'||**s>'9')return -1;
 char *end;errno=0;unsigned long long value=strtoull(*s,&end,10);
 if(errno||*end!=',')return -1;
 *v=value;*s=end+1;return 0;
}
static int parse(const char *s,size_t len,unsigned *facility,uint64_t *seq) {
 uint64_t pri,stamp;const char *cursor=s;
 if(strlen(s)!=len||decimal(&cursor,&pri)||decimal(&cursor,seq)||decimal(&cursor,&stamp)||pri>1023)return -1;
 const char *semi=memchr(cursor,';',len-(size_t)(cursor-s));
 if(!semi)return -1;
 *facility=(unsigned)(pri>>3);return 0;
}
static int is_fault(const char *s) {
 static const char *const markers[]={"WARNING:","BUG:","kernel BUG", "Call trace:","Call Trace:","Oops:","Internal error:","Kernel panic", "Unable to handle kernel", "KASAN:","TXFREE truncated","soft lockup","hard LOCKUP"};
 for(size_t i=0;i<sizeof(markers)/sizeof(markers[0]);i++)if(strstr(s,markers[i]))return 1;
 return 0;
}
static void pop(void) {
 if(!count)return;
 ring_bytes-=ring[first].len;free(ring[first].text);ring[first].text=NULL;
 first=(first+1)%RING_SLOTS;count--;
}
static int retain(const char *s,size_t len) {
 if(len>PRE_MAX)return -1;
 while(count&&(count==RING_SLOTS||ring_bytes+len>PRE_MAX))pop();
 unsigned index=(first+count)%RING_SLOTS;
 ring[index].text=malloc(len);if(!ring[index].text)return -1;
 memcpy(ring[index].text,s,len);ring[index].len=len;ring_bytes+=len;count++;return 0;
}
static int append(const char *s,size_t len) {
 if(capped)return 0;
 if(len>OUTPUT_MAX-written){capped=1;return 0;}
 if(write_all(logfile,s,len)||fdatasync(logfile))return -1;
 written+=len;return 0;
}
static int latch(uint64_t seq) {
 fault=1;fault_seq=seq;
 logfile=openat(dirfd,"first-fault.kmsg",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(logfile<0)return -1;
 for(unsigned i=0;i<count;i++) {
  struct record *r=&ring[(first+i)%RING_SLOTS];if(append(r->text,r->len))return -1;
 }
 if(fsync(dirfd)||status("fault.json"))return -1;
 while(count)pop();
 return 0;
}
static int read_boot(void) {
 int fd=open("/proc/sys/kernel/random/boot_id",O_RDONLY|O_CLOEXEC);if(fd<0)return -1;
 ssize_t n=read(fd,boot,sizeof(boot)-1);close(fd);if(n!=36)return -1;
 for(int i=0;i<36;i++) {
  if(i==8||i==13||i==18||i==23){if(boot[i]!='-')return -1;}
  else if(!((boot[i]>='0'&&boot[i]<='9')||(boot[i]>='a'&&boot[i]<='f')))return -1;
 }
 return 0;
}
static int open_directory(const char *path) {
 /* Walk existing parent directories without following symbolic links. */
 if(!path||path[0]!='/'||strlen(path)>=PATH_MAX)return -1;
 char copy[PATH_MAX];strcpy(copy,path+1);char *save=NULL,*part=strtok_r(copy,"/",&save);
 int parent=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(parent<0)return -1;
 if(!part){close(parent);return -1;}
 while(part) {
  char *next=strtok_r(NULL,"/",&save);
  if(!strcmp(part,".")||!strcmp(part,"..")||!part[0]){close(parent);return -1;}
  if(!next) {
   if(mkdirat(parent,part,0700)){close(parent);return -1;}
   int fd=openat(parent,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
   int err=fsync(parent);close(parent);if(err&&fd>=0){close(fd);return -1;}return fd;
  }
  int fd=openat(parent,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  close(parent);if(fd<0)return -1;parent=fd;part=next;
 }
 close(parent);return -1;
}
int main(int argc,char **argv) {
 if(argc!=3){fprintf(stderr,"usage: xr-kmsg-capture NEW_ABSOLUTE_DIRECTORY SECONDS(1..600)\n");return 2;}
 char *end;errno=0;unsigned long seconds=strtoul(argv[2],&end,10);
 if(errno||!*argv[2]||*end||seconds<1||seconds>600||read_boot())return 2;
 umask(077);dirfd=open_directory(argv[1]);if(dirfd<0){perror("capture directory");return 2;}
 int input=open("/dev/kmsg",O_RDONLY|O_NONBLOCK|O_CLOEXEC);
 if(input<0){failed=1;status("closed.json");close(dirfd);return 2;}
 struct sigaction sa={.sa_handler=stopped};sigemptyset(&sa.sa_mask);sigaction(SIGTERM,&sa,NULL);sigaction(SIGINT,&sa,NULL);
 char *buf=malloc(RECORD_MAX+1);if(!buf){close(input);close(dirfd);return 2;}
 uint64_t deadline=now_ms()+seconds*1000,tail_deadline=0;
 int ready=0;
 if(status("started.json")){failed=1;goto done;}
 while(!stop&&now_ms()<deadline&&(!tail_deadline||now_ms()<tail_deadline)) {
  ssize_t n=read(input,buf,RECORD_MAX);
  if(n<0) {
   if(errno==EINTR)continue;
   if(errno==EPIPE){gaps++;failed=1;break;}
   if(errno==EAGAIN){
    if(!ready&&!fault&&!gaps&&have_seq){if(status("ready.json")){failed=1;break;}ready=1;}
    struct pollfd p={.fd=input,.events=POLLIN};if(poll(&p,1,100)<0&&errno!=EINTR){failed=1;break;}continue;
   }
   failed=1;break;
  }
  if(!n){failed=1;break;}
  buf[n]=0;unsigned facility;uint64_t seq;
  if(parse(buf,(size_t)n,&facility,&seq)){failed=1;break;}
  if(have_seq&&seq!=last_seq+1)gaps++;
  if(!have_seq){first_seq=seq;have_seq=1;if(seq)gaps++;}
  last_seq=seq;records++;
  if(gaps){failed=1;break;}
  if(!fault) {
   if(retain(buf,(size_t)n)){failed=1;break;}
   /* /dev/kmsg userspace injections are LOG_USER, never LOG_KERN. */
   if(facility==0&&is_fault(strchr(buf,';')+1)) {
    if(latch(seq)){failed=1;break;}tail_deadline=now_ms()+10000;
   }
  } else if(append(buf,(size_t)n)){failed=1;break;}
 }
done:
 if(logfile>=0){if(fsync(logfile))failed=1;if(close(logfile))failed=1;}
 if(status("closed.json"))failed=1;
 while(count)pop();
 free(buf);close(input);close(dirfd);
 return failed||gaps||capped?1:0;
}
