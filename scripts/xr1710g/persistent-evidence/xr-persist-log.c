/* SPDX-License-Identifier: GPL-2.0-only
 * Bounded persistent kernel evidence recorder, independent of SSH and NPU.
 * No hardware/configuration/network/reboot operations. New output directory
 * required; existing evidence is never reused or overwritten.
 *
 * Unlike the older fault-triggered recorder, every batch is durable BEFORE
 * a fault is recognized. Commit lines follow fdatasync(log); incomplete last
 * commits are ignored offline. A stopped CPU/storage device cannot write.
 * CRC32 detects torn/corrupt prefixes, not authenticity or causality.
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
#define LOG_MAX 1048576u
#define BATCH_MAX 65536u
#define COMMIT_MS 2000u
#define COMMIT_MAX 512u
static volatile sig_atomic_t stop;
static int directory=-1,logfile=-1,commits=-1;
static uint64_t count,first_seq,last_seq,gaps,written,generation,last_sync;
static uint32_t crc=0xffffffffu;
static int have_seq,fault,capped,failed;
static char boot[37];
static int notify_fd=-1;

static uint64_t now_ms(void) {
 struct timespec t;
 if(clock_gettime(CLOCK_MONOTONIC,&t))return UINT64_MAX;
 return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
}
static void stopping(int sig) {(void)sig;stop=1;}
static int write_all(int fd,const void *data,size_t bytes) {
 const char *p=data;
 while(bytes) {
  ssize_t n=write(fd,p,bytes);
  if(n<0&&errno==EINTR)continue;
  if(n<=0)return -1;
  p+=n;bytes-=(size_t)n;
 }
 return 0;
}
static uint32_t crc_add(uint32_t value,const char *p,size_t n) {
 while(n--) {
  value^=(unsigned char)*p++;
  for(int i=0;i<8;i++)value=(value>>1)^(0xedb88320u&(0u-(value&1u)));
 }
 return value;
}
static int boot_id(void) {
 int fd=open("/proc/sys/kernel/random/boot_id",O_RDONLY|O_CLOEXEC);
 if(fd<0)return -1;
 ssize_t n=read(fd,boot,36);close(fd);
 if(n!=36)return -1;
 for(unsigned i=0;i<36;i++) {
  if(i==8||i==13||i==18||i==23) {if(boot[i]!='-')return -1;}
  else if(!((boot[i]>='0'&&boot[i]<='9')||(boot[i]>='a'&&boot[i]<='f')))return -1;
 }
 return 0;
}
/* Walk without following symlinks; create only a fresh final directory. */
static int new_directory(const char *path) {
 if(!path||path[0]!='/'||strlen(path)>=PATH_MAX)return -1;
 char copy[PATH_MAX];strcpy(copy,path+1);
 char *save=NULL,*part=strtok_r(copy,"/",&save);
 int parent=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
 if(parent<0||!part) {if(parent>=0)close(parent);return -1;}
 while(part) {
  char *next=strtok_r(NULL,"/",&save);
  if(!strcmp(part,".")||!strcmp(part,"..")) {close(parent);return -1;}
  if(!next) {
   if(mkdirat(parent,part,0700)) {close(parent);return -1;}
   int fd=openat(parent,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
   int rc=fsync(parent);close(parent);
   if(rc&&fd>=0) {close(fd);return -1;}
   return fd;
  }
  int fd=openat(parent,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  close(parent);if(fd<0)return -1;parent=fd;part=next;
 }
 close(parent);return -1;
}
static int fresh_file(const char *name,const char *data) {
 int fd=openat(directory,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;
 int rc=write_all(fd,data,strlen(data));
 if(fsync(fd))rc=-1;
 if(close(fd))rc=-1;
 if(fsync(directory))rc=-1;
 return rc;
}
static int decimal(const char **p,uint64_t *v) {
 if(**p<'0'||**p>'9')return -1;
 char *end;errno=0;unsigned long long n=strtoull(*p,&end,10);
 if(errno||*end!=',')return -1;
 *v=n;*p=end+1;return 0;
}
static int parse(const char *p,size_t n,unsigned *facility,uint64_t *seq) {
 if(strlen(p)!=n)return -1;
 uint64_t priority,stamp;const char *cursor=p;
 if(decimal(&cursor,&priority)||decimal(&cursor,seq)||decimal(&cursor,&stamp)||priority>1023)return -1;
 if(!memchr(cursor,';',n-(size_t)(cursor-p)))return -1;
 *facility=(unsigned)(priority>>3);return 0;
}
static int fault_marker(const char *p) {
 static const char *markers[]={"Internal error:","Oops:","Kernel panic","BUG:","WARNING:","Unable to handle kernel","soft lockup","hard LOCKUP","KASAN:"};
 for(size_t i=0;i<sizeof(markers)/sizeof(markers[0]);i++)if(strstr(p,markers[i]))return 1;
 return 0;
}
static int commit(const char *kind) {
 if(generation>=COMMIT_MAX) {capped=1;return -1;}
 if(fdatasync(logfile))return -1;
 char line[768];uint64_t when=now_ms();
 if(when==UINT64_MAX)return -1;
 int n=snprintf(line,sizeof(line),"{\"schema\":1,\"bootID\":\"%s\",\"generation\":%"PRIu64",\"kind\":\"%s\",\"monotonicMs\":%"PRIu64",\"bytes\":%"PRIu64",\"crc32\":%"PRIu32",\"records\":%"PRIu64",\"firstSeq\":%"PRIu64",\"lastSeq\":%"PRIu64",\"gaps\":%"PRIu64",\"faultSeen\":%s,\"failed\":%s,\"capped\":%s}\n",
 boot,generation+1,kind,when,written,crc^0xffffffffu,count,first_seq,last_seq,gaps,fault?"true":"false",failed?"true":"false",capped?"true":"false");
 if(n<0||(size_t)n>=sizeof(line)||write_all(commits,line,(size_t)n)||fdatasync(commits))return -1;
 generation++;last_sync=when;return 0;
}
static int consume(const char *p,size_t n,int *urgent) {
 unsigned facility;uint64_t seq;
 if(parse(p,n,&facility,&seq))return -1;
 if(have_seq&&(last_seq==UINT64_MAX||seq!=last_seq+1))gaps++;
 if(!have_seq) {first_seq=seq;have_seq=1;if(seq!=0)gaps++;}
 if(n>LOG_MAX-written) {capped=1;return 1;}
 if(write_all(logfile,p,n))return -1;
 crc=crc_add(crc,p,n);written+=n;count++;last_seq=seq;
 const char *message=strchr(p,';')+1;
 *urgent=0;
 if(facility==0&&!fault&&fault_marker(message)) {fault=1;*urgent=1;}
 if(facility==0&&strstr(message,"XR_IABT_DIE_END"))*urgent=1;
 return 0;
}

/* Fork+setsid+handshake: original shell/SSH may exit without stopping logging.
 * Parent returns success only after the first durable commit. */
static int detach(void) {
 int pipefd[2];if(pipe2(pipefd,O_CLOEXEC))return -1;
 pid_t pid=fork();
 if(pid<0) {close(pipefd[0]);close(pipefd[1]);return -1;}
 if(pid) {
  close(pipefd[1]);struct pollfd p={.fd=pipefd[0],.events=POLLIN};char ch=0;
  int ready=poll(&p,1,8000)==1&&read(pipefd[0],&ch,1)==1&&ch=='R';
  close(pipefd[0]);if(!ready)kill(pid,SIGTERM);
  return ready?1:-1;
 }
 close(pipefd[0]);notify_fd=pipefd[1];
 if(setsid()<0)_exit(2);
 int null=open("/dev/null",O_RDWR);
 if(null<0)_exit(2);
 for(int fd=0;fd<3;fd++)if(dup2(null,fd)<0)_exit(2);
 if(null>2)close(null);
 return 0;
}

int main(int argc,char **argv) {
 int daemon=argc==4&&!strcmp(argv[3],"--daemon");
 if((argc!=3&&!daemon)||boot_id())return 2;
 char *end;errno=0;unsigned long seconds=strtoul(argv[2],&end,10);
 if(errno||!*argv[2]||*end||seconds<1||seconds>600)return 2;
#ifndef XR_PERSIST_FIXTURE
 if(geteuid()!=0)return 2;
#endif
 struct sigaction sa={.sa_handler=stopping};sigemptyset(&sa.sa_mask);
 sigaction(SIGTERM,&sa,NULL);sigaction(SIGINT,&sa,NULL);
 signal(SIGHUP,SIG_IGN);signal(SIGPIPE,SIG_IGN);
 if(daemon) {int rc=detach();if(rc!=0)return rc==1?0:2;}
 umask(077);directory=new_directory(argv[1]);
 if(directory<0)return 2;
 logfile=openat(directory,"kernel.kmsg",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 commits=openat(directory,"commits.jsonl",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(logfile<0||commits<0||fsync(directory))return 2;
 uint64_t start=now_ms(),deadline=start+(uint64_t)seconds*1000;
 char meta[768];
 int n=snprintf(meta,sizeof(meta),"{\"schema\":1,\"bootID\":\"%s\",\"pid\":%ld,\"startMs\":%"PRIu64",\"deadlineMs\":%"PRIu64",\"seconds\":%lu,\"logCap\":%u,\"commitIntervalMs\":%u,\"commitCap\":%u,\"daemon\":%s}\n",boot,(long)getpid(),start,deadline,seconds,LOG_MAX,COMMIT_MS,COMMIT_MAX,daemon?"true":"false");
 if(start==UINT64_MAX||n<0||(size_t)n>=sizeof(meta)||fresh_file("meta.json",meta))return 2;
 int input=-1;
#ifdef XR_PERSIST_FIXTURE
 const char *input_path=getenv("XR_PERSIST_INPUT");
 if(input_path)input=open(input_path,O_RDONLY|O_NONBLOCK|O_CLOEXEC);
#else
 input=open("/dev/kmsg",O_RDONLY|O_NONBLOCK|O_CLOEXEC);
#endif
 if(input<0)return 2;
 if(commit("start"))return 2;
 if(notify_fd>=0) {if(write_all(notify_fd,"R",1))stop=1;close(notify_fd);notify_fd=-1;}
 char *buf=malloc(RECORD_MAX+1);if(!buf)return 2;
 uint64_t batch_start=written;
 while(!stop&&now_ms()<deadline&&!capped&&!failed) {
  ssize_t got;
#ifdef XR_PERSIST_FIXTURE
  /* Replay mode deliberately reads one raw kmsg line per record. Never
   * present in the production binary and never opens an arbitrary input. */
  got=0;
  while(got<(ssize_t)RECORD_MAX) {ssize_t v=read(input,buf+got,1);if(v<=0)break;if(buf[got++]=='\n')break;}
  if(!got) {struct timespec t={.tv_nsec=20000000};nanosleep(&t,NULL);got=-1;errno=EAGAIN;}
#else
  got=read(input,buf,RECORD_MAX);
#endif
  if(got>0) {
   buf[got]=0;int urgent=0;int rc=consume(buf,(size_t)got,&urgent);
   if(rc<0)failed=1;
   if(rc>0)capped=1;
   if(urgent) {if(commit("fault"))failed=1;batch_start=written;}
  } else if(got==0)failed=1;
  else if(errno==EPIPE)gaps++;
  else if(errno!=EAGAIN&&errno!=EINTR)failed=1;
  if(written-batch_start>=BATCH_MAX||now_ms()-last_sync>=COMMIT_MS) {
   if(commit("periodic"))failed=1;
   batch_start=written;
  }
  if(got<0&&errno==EAGAIN) {struct pollfd p={.fd=input,.events=POLLIN};(void)poll(&p,1,50);}
 }
 if(commit("end"))failed=1;
 char closed[160];snprintf(closed,sizeof(closed),"{\"schema\":1,\"stopped\":%s,\"failed\":%s,\"capped\":%s,\"generation\":%"PRIu64"}\n",stop?"true":"false",failed?"true":"false",capped?"true":"false",generation);
 if(fresh_file("closed.json",closed))failed=1;
 free(buf);close(input);close(logfile);close(commits);close(directory);
 return failed||capped?1:0;
}
