/* SPDX-License-Identifier: GPL-2.0-only
 * Opt-in diagnostic recovery. This program never enables NPU or changes UCI.
 * A separate deadline child survives loss of the monitoring process. Neither
 * userspace nor a generic VM can guarantee recovery from a hardware lockup.
 */
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/reboot.h>
#include <sys/prctl.h>
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

static volatile sig_atomic_t interrupted;
static int journal=-1;
static char boot[37];
static uint64_t expires;
static pid_t capture=-1, deadline_pid=-1;
static int reaped;

static uint64_t milliseconds(void) {
 struct timespec t;
 if(clock_gettime(CLOCK_MONOTONIC,&t))_exit(111);
 return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
}
static void pause_ms(unsigned n) {
 struct timespec t={.tv_sec=n/1000,.tv_nsec=(long)(n%1000)*1000000};
 while(nanosleep(&t,&t)&&errno==EINTR){}
}
static void stop(int sig) { (void)sig;interrupted=1; }
static int full_write(int fd,const char *s,size_t len) {
 while(len){ssize_t n=write(fd,s,len);if(n<0&&errno==EINTR)continue;
  if(n<=0)return -1;
  s+=n;len-=(size_t)n;
 }
 return 0;
}
static int uuid(const char *s) {
 if(strlen(s)!=36)return 0;
 for(int i=0;i<36;i++) {
  if(i==8||i==13||i==18||i==23){if(s[i]!='-')return 0;}
  else if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
 }
 return 1;
}
static int boot_id(void) {
 int fd=open("/proc/sys/kernel/random/boot_id",O_RDONLY|O_CLOEXEC);
 if(fd<0)return -1;
 ssize_t n=read(fd,boot,36);close(fd);
 return n==36&&uuid(boot)?0:-1;
}
static int make_journal(const char *path) {
 if(!path||path[0]!='/'||strlen(path)>=PATH_MAX)return -1;
 char copy[PATH_MAX];strcpy(copy,path+1);char *save=NULL,*part=strtok_r(copy,"/",&save);
 int parent=open("/",O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(parent<0)return -1;
 if(!part){close(parent);return -1;}
 while(part) {
  char *next=strtok_r(NULL,"/",&save);
  if(!strcmp(part,".")||!strcmp(part,"..")){close(parent);return -1;}
  if(!next&&mkdirat(parent,part,0700)){close(parent);return -1;}
  int fd=openat(parent,part,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
  if(!next&&fsync(parent)){if(fd>=0)close(fd);close(parent);return -1;}
  close(parent);if(fd<0)return -1;
  if(!next)return fd;
  parent=fd;part=next;
 }
 close(parent);return -1;
}
static int note(const char *name,const char *reason) {
 char text[512];
 int n=snprintf(text,sizeof(text),"{\"schema\":1,\"bootID\":\"%s\",\"pid\":%ld,\"collectorPID\":%ld,\"deadlinePID\":%ld,\"monotonicMs\":%"PRIu64",\"deadlineMs\":%"PRIu64",\"reason\":\"%s\"}\n",
  boot,(long)getpid(),(long)capture,(long)deadline_pid,milliseconds(),expires,reason);
 if(n<0||(size_t)n>=sizeof(text))return -1;
 int fd=openat(journal,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return -1;
 int result=full_write(fd,text,(size_t)n);
 if(fsync(fd))result=-1;
 if(close(fd))result=-1;
 if(fsync(journal))result=-1;
 return result;
}
static int present(const char *name) {
 struct stat st;
 if(!fstatat(journal,name,&st,AT_SYMLINK_NOFOLLOW))return 1;
 return errno==ENOENT?0:1; /* A read error is not evidence of health. */
}
static int capture_alive(void) {
 if(reaped)return 0;
 int status;pid_t p=waitpid(capture,&status,WNOHANG);
 if(p==capture||(p<0&&errno!=EINTR)){reaped=1;return 0;}
 return 1;
}
static int healthy_ready(const char *data,pid_t child,uint64_t now) {
 char id[37]={0},fault[6]={0},failed[6]={0},capped[6]={0};long pid;
 uint64_t records,first,last,faultseq,gaps,stamp;size_t written;int used=0;
 int n=sscanf(data,"{\"schema\":1,\"bootID\":\"%36[0-9a-f-]\",\"pid\":%ld,\"records\":%"SCNu64",\"firstSeq\":%"SCNu64",\"lastSeq\":%"SCNu64",\"fault\":%5[a-z],\"faultSeq\":%"SCNu64",\"gaps\":%"SCNu64",\"failed\":%5[a-z],\"capped\":%5[a-z],\"written\":%zu,\"monotonicMs\":%"SCNu64"}\n%n",
  id,&pid,&records,&first,&last,fault,&faultseq,&gaps,failed,capped,&written,&stamp,&used);
 return n==12&&used>0&&data[used]==0&&uuid(id)&&!strcmp(id,boot)&&pid==child&&
  records>0&&first==0&&last!=UINT64_MAX&&records==last+1&&
  !strcmp(fault,"false")&&!strcmp(failed,"false")&&!strcmp(capped,"false")&&
  !faultseq&&!gaps&&!written&&stamp<=now&&now-stamp<=5000;
}
static int ready(void) {
 int directory=openat(journal,"capture",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
 if(directory<0)return 0;
 int fd=openat(directory,"ready.json",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);close(directory);
 if(fd<0)return 0;
 struct stat st;char data[1024];
 int okay=!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==0&&(st.st_mode&0777)==0600&&st.st_size>0&&st.st_size<(off_t)sizeof(data);
 ssize_t n=okay?read(fd,data,sizeof(data)-1):-1;close(fd);
 if(!okay||n!=st.st_size)return 0;
 data[n]=0;return healthy_ready(data,capture,milliseconds());
}
static void force_reboot(void) {
 /* The independent deadline must not block on fsync or a shell child. */
 reboot(RB_AUTOBOOT);
 _exit(112); /* No fake success if the syscall was denied. */
}
static int start_deadline(void) {
 int pipefd[2];if(pipe2(pipefd,O_CLOEXEC))return -1;
 deadline_pid=fork();
 if(deadline_pid<0){close(pipefd[0]);close(pipefd[1]);return -1;}
 if(!deadline_pid) {
  close(pipefd[0]);close(journal);
  signal(SIGTERM,SIG_IGN);signal(SIGINT,SIG_IGN);signal(SIGHUP,SIG_IGN);
  setsid();
  if(full_write(pipefd[1],"R",1))_exit(113);
  close(pipefd[1]);
  struct timespec due={.tv_sec=(time_t)(expires/1000),.tv_nsec=(long)(expires%1000)*1000000};
  int result;do result=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&due,NULL);while(result==EINTR);
  force_reboot();
 }
 close(pipefd[1]);struct pollfd p={.fd=pipefd[0],.events=POLLIN};char ch=0;
 int result=poll(&p,1,1000)==1&&read(pipefd[0],&ch,1)==1&&ch=='R';
 close(pipefd[0]);return result?0:-1;
}
/* Fixed scalar-only debugfs endpoint. Run in a separate bounded child: a
 * driver mutex or flash I/O must never postpone the recovery deadline.
 * The diagnostic exports counts/lengths, never frame contents or token IDs.
 */
static int copy_metadata(int input,int output,size_t *copied,size_t limit) {
 char data[1024];*copied=0;
 /* Fixed internal budgets only, never an operator-selected read size. */
 if(limit!=16384&&limit!=65536){errno=EINVAL;return -1;}
 while(*copied<limit) {
  size_t want=limit-*copied;if(want>sizeof(data))want=sizeof(data);
  ssize_t n=read(input,data,want);
  if(n<0&&errno==EINTR)continue;
  if(n<0)return -1;
  if(!n)return 0;
  if(full_write(output,data,(size_t)n))return -1;
  *copied+=(size_t)n;
 }
 char extra;ssize_t n;
 do n=read(input,&extra,1);while(n<0&&errno==EINTR);
 return n==0?0:n>0?1:-1;
}
static void snapshot_one(const char *endpoint,const char *filename,size_t limit) {
 pid_t worker=fork();if(worker)return;
 signal(SIGALRM,SIG_DFL);alarm(2);
 int output=openat(journal,filename,
                   O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 if(output<0)_exit(115);
 char line[256];
 int n=snprintf(line,sizeof(line),"schema=1 bootID=%s monotonicMs=%"PRIu64"\n",
                boot,milliseconds());
 if(n<0||(size_t)n>=sizeof(line)||full_write(output,line,(size_t)n))_exit(116);
 /* This read may wait on the device mutex; only the child can be blocked. */
 int input=open(endpoint,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
 size_t copied=0;int result=-1;
 if(input>=0){result=copy_metadata(input,output,&copied,limit);close(input);}
 n=snprintf(line,sizeof(line),"snapshot_status=%s bytes=%zu\n",
            result==0?"complete":result==1?"capped":"failed",copied);
 if(n<0||(size_t)n>=sizeof(line)||full_write(output,line,(size_t)n))_exit(116);
 if(fsync(output)||close(output)||fsync(journal))_exit(117);
 _exit(result?118:0);
}
static void snapshot_metadata(void) {
 /* Independent children: one blocked endpoint cannot suppress the other
  * snapshot or postpone the independent recovery deadline. */
 snapshot_one("/sys/kernel/debug/ieee80211/phy0/mt76/xr_token_info",
              "fault-token-metadata.txt",16384);
 snapshot_one("/sys/kernel/debug/xr_npu_addresses/snapshot",
              "fault-npu-addresses.txt",16384);
 /* Eight harts with 32 committed records each can exceed 16 KiB. */
 snapshot_one("/sys/kernel/debug/xr_npu_producer/snapshot",
              "fault-npu-producer.txt",65536);
}
static void recover(const char *reason,int tail) {
 unlinkat(journal,"ready.json",0);
 if(tail)snapshot_metadata();
 note("aborted.json",reason);
 /* The first-fault file appears before its fsynced prehistory and status.
  * Allow the bounded prehistory flush plus the collector's 10s tail. */
 uint64_t until=milliseconds()+(tail?20000:0);
 while(tail&&milliseconds()<until&&milliseconds()+1000<expires&&capture_alive())pause_ms(100);
 if(capture>0&&capture_alive())kill(capture,SIGTERM);
 /* SIGTERM asks the collector to persist its retained records and closed
  * status. Waiting for its child exit is bounded; the independent deadline
  * still forces recovery if flash I/O or the collector is stuck. */
 uint64_t close_limit=milliseconds()+2000;
 while(capture>0&&capture_alive()&&milliseconds()<close_limit&&
       milliseconds()+1000<expires)pause_ms(50);
 note("recovery.json",reason);
 pid_t syncing=fork();
 if(!syncing){sync();_exit(0);}
 uint64_t limit=milliseconds()+2000;
 if(syncing>0)while(milliseconds()<limit&&waitpid(syncing,NULL,WNOHANG)==0)pause_ms(50);
 force_reboot();
}
int main(int argc,char **argv) {
 if(argc!=3||geteuid()!=0||boot_id())return 2;
 char *end;errno=0;unsigned long seconds=strtoul(argv[2],&end,10);
 if(errno||!*argv[2]||*end||seconds<15||seconds>240)return 2;
 char path[PATH_MAX];int n=snprintf(path,sizeof(path),"%s/capture",argv[1]);
 if(n<0||(size_t)n>=sizeof(path))return 2;
 umask(077);journal=make_journal(argv[1]);if(journal<0)return 2;
 expires=milliseconds()+seconds*1000;
 struct sigaction sa={.sa_handler=stop};sigemptyset(&sa.sa_mask);
 sigaction(SIGTERM,&sa,NULL);sigaction(SIGINT,&sa,NULL);sigaction(SIGHUP,&sa,NULL);
 if(start_deadline())recover("deadline-start-failed",0);
 if(note("armed.json","deadline-armed"))recover("journal-failed",0);
 capture=fork();
 if(capture<0)recover("capture-fork-failed",0);
 if(!capture) {
  close(journal);
  char duration[16];snprintf(duration,sizeof(duration),"%lu",seconds+15);
  execl("/usr/libexec/xr-diag-capture","xr-diag-capture",path,duration,(char *)NULL);
  _exit(114);
 }
 uint64_t started=milliseconds();int published=0;
 /* The old supervisor and hard-deadline child raced at exactly expires.
  * Begin orderly shutdown early; do not postpone the independent deadline. */
 while(milliseconds()+10000<expires) {
  if(interrupted)recover("supervisor-signal",0);
  if(present("capture/first-fault.kmsg")||present("capture/fault.json"))recover("kernel-fault",1);
  if(present("abort"))recover("operator-abort",0);
  if(present("capture/closed.json")||!capture_alive())recover("capture-stopped",0);
  if(!published&&ready()) {
   if(note("ready.json","capture-and-deadline-ready"))recover("ready-write-failed",0);
   published=1;
  }
  if(!published&&milliseconds()-started>=5000)recover("capture-not-ready",0);
  pause_ms(100);
 }
 recover("deadline",0);
 return 112;
}
