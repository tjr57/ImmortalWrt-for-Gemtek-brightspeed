/* SPDX-License-Identifier: GPL-2.0-only
 * One-boot mt76 parameter selection behind independently verified recovery.
 * Module options exist only in /tmp and no driver is unloaded or reset.
 */
#define _GNU_SOURCE
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <json-c/json.h>

static int journal=-1;
static char boot[37],record[PATH_MAX];
static uint64_t now_ms(void) {
 struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return UINT64_MAX;
 return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
}
static int read_file(const char *path,char *data,size_t size) {
 int fd=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return -1;
 ssize_t n=read(fd,data,size-1);close(fd);
 if(n<0||(size_t)n==size-1)return -1;
 data[n]=0;return (int)n;
}
static int uuid(const char *s) {
 if(strlen(s)!=36)return 0;
 for(int i=0;i<36;i++) {
  if(i==8||i==13||i==18||i==23){if(s[i]!='-')return 0;}
  else if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
 }
 return 1;
}
static int absent(const char *path) {
 struct stat st;return lstat(path,&st)<0&&errno==ENOENT;
}
static int missing_note(const char *name) {
 struct stat st;return fstatat(journal,name,&st,AT_SYMLINK_NOFOLLOW)<0&&errno==ENOENT;
}
static int number(struct json_object *o,const char *name,int64_t *value) {
 struct json_object *v;
 if(!json_object_object_get_ex(o,name,&v)||!json_object_is_type(v,json_type_int))return 0;
 *value=json_object_get_int64(v);return *value>=0;
}
static int text_equal(struct json_object *o,const char *name,const char *expected) {
 struct json_object *v;
 return json_object_object_get_ex(o,name,&v)&&json_object_is_type(v,json_type_string)&&
  json_object_get_string_len(v)==(int)strlen(expected)&&!strcmp(json_object_get_string(v),expected);
}
static int false_value(struct json_object *o,const char *name) {
 struct json_object *v;
 return json_object_object_get_ex(o,name,&v)&&json_object_is_type(v,json_type_boolean)&&!json_object_get_boolean(v);
}
static struct json_object *read_json_at(const char *name) {
 int fd=openat(journal,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd<0)return NULL;
 struct stat st;char data[2048];
 int valid=!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==0&&(st.st_mode&0777)==0600&&st.st_size>0&&st.st_size<(off_t)sizeof(data);
 ssize_t n=valid?read(fd,data,sizeof(data)-1):-1;close(fd);
 if(!valid||n!=st.st_size)return NULL;
 data[n]=0;
 struct json_tokener *tok=json_tokener_new();if(!tok)return NULL;
 json_tokener_set_flags(tok,JSON_TOKENER_STRICT);
 struct json_object *o=json_tokener_parse_ex(tok,data,(int)n);
 if(json_tokener_get_error(tok)!=json_tokener_success||!json_object_is_type(o,json_type_object)){
  json_object_put(o);o=NULL;
 }
 size_t used=json_tokener_get_parse_end(tok);
 if(o)for(size_t i=used;i<(size_t)n;i++)if(data[i]!=' '&&data[i]!='\n'&&data[i]!='\t'&&data[i]!='\r'){json_object_put(o);o=NULL;break;}
 json_tokener_free(tok);return o;
}
static int process_matches(int64_t pid,const char *program,const char *directory,int64_t parent) {
 if(pid<=1||pid>INT_MAX)return 0;
 char path[128],data[4096];snprintf(path,sizeof(path),"/proc/%ld/cmdline",(long)pid);
 int n=read_file(path,data,sizeof(data));size_t a=strlen(program)+1,b=strlen(directory)+1;
 if(n<=0||(size_t)n<a+b||memcmp(data,program,a)||memcmp(data+a,directory,b))return 0;
 snprintf(path,sizeof(path),"/proc/%ld/stat",(long)pid);
 if(read_file(path,data,sizeof(data))<0)return 0;
 const char *end=strrchr(data,')');char state;long ppid;
 return end&&sscanf(end+1," %c %ld",&state,&ppid)==2&&state!='Z'&&state!='X'&&(!parent||ppid==parent);
}
static int capture_record_valid(struct json_object *o,int64_t pid,uint64_t now) {
 int64_t actual,first,last,records,gaps,stamp,schema;
 return o&&number(o,"schema",&schema)&&schema==1&&text_equal(o,"bootID",boot)&&
  number(o,"pid",&actual)&&actual==pid&&number(o,"firstSeq",&first)&&first==0&&
  number(o,"lastSeq",&last)&&last<INT64_MAX&&number(o,"records",&records)&&records==last+1&&
  number(o,"gaps",&gaps)&&gaps==0&&false_value(o,"fault")&&false_value(o,"failed")&&false_value(o,"capped")&&
  number(o,"monotonicMs",&stamp)&&(uint64_t)stamp<=now;
}
static int guard_valid(unsigned minimum_seconds) {
 struct json_object *g=read_json_at("ready.json"),*c=read_json_at("capture/ready.json");
 int64_t schema=0,pid=0,collector=0,deadline=0,expires=0,stamp=0;uint64_t now=now_ms();
 char capture_dir[PATH_MAX];int n=snprintf(capture_dir,sizeof(capture_dir),"%s/capture",record);
 int valid=g&&c&&n>0&&(size_t)n<sizeof(capture_dir)&&number(g,"schema",&schema)&&schema==1&&
  text_equal(g,"bootID",boot)&&text_equal(g,"reason","capture-and-deadline-ready")&&
  number(g,"pid",&pid)&&number(g,"collectorPID",&collector)&&number(g,"deadlinePID",&deadline)&&
  pid!=collector&&pid!=deadline&&collector!=deadline&&
  number(g,"deadlineMs",&expires)&&(uint64_t)expires>=now+(uint64_t)minimum_seconds*1000&&
  (uint64_t)expires-now<=240000&&number(g,"monotonicMs",&stamp)&&(uint64_t)stamp<=now&&
  capture_record_valid(c,collector,now)&&
  missing_note("abort")&&missing_note("aborted.json")&&missing_note("capture/first-fault.kmsg")&&missing_note("capture/fault.json")&&missing_note("capture/closed.json")&&
  process_matches(pid,"/usr/libexec/xr-diag-recovery",record,0)&&
  process_matches(deadline,"/usr/libexec/xr-diag-recovery",record,pid)&&
  process_matches(collector,"xr-diag-capture",capture_dir,pid);
 json_object_put(g);json_object_put(c);return valid;
}
static int write_note(const char *name,const char *reason) {
 char data[256];int n=snprintf(data,sizeof(data),"{\"schema\":1,\"bootID\":\"%s\",\"monotonicMs\":%llu,\"reason\":\"%s\"}\n",boot,(unsigned long long)now_ms(),reason);
 if(n<0||(size_t)n>=sizeof(data))return -1;
 int fd=openat(journal,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);if(fd<0)return -1;
 int result=write(fd,data,(size_t)n)==n?0:-1;
 if(fsync(fd))result=-1;
 if(close(fd))result=-1;
 if(fsync(journal))result=-1;
 return result;
}
static int reject(const char *reason) {
 write_note("activation-failed.json",reason);
 /* Let the first-fault collector finish its bounded tail; do not replace
  * fault recovery with an immediate operator-style abort. */
 if(missing_note("capture/first-fault.kmsg")&&missing_note("capture/fault.json"))write_note("abort",reason);
 return 1;
}
static int parameter_is(const char *name,char value) {
 char path[256],data[8];snprintf(path,sizeof(path),"/sys/module/mt76/parameters/%s",name);
 return read_file(path,data,sizeof(data))==2&&data[0]==value&&data[1]=='\n';
}
static int ppe_off(void) {
 const char *names[]={"/sys/module/airoha_eth/parameters/ppe_bind_enable","/sys/module/airoha_eth/parameters/ppe_bridge_bind_enable"};
 for(unsigned i=0;i<2;i++){
  char data[8];if(absent(names[i]))continue;
  if(read_file(names[i],data,sizeof(data))!=2||strcmp(data,"N\n"))return 0;
 }
 return 1;
}

/* A successful module insertion alone does not establish the loaded firmware
 * identity or the trace alias. The fixed reader validates both before output.
 * Before mt76 attaches, every per-hart record area must still be empty. */
static int producer_empty(const char *data,size_t bytes) {
 static const char expected[]=
  "schema=2 atomic=0 source=producer-scalar record_words=12\n"
  "hart=0 count=0\n" "hart=1 count=0\n" "hart=2 count=0\n" "hart=3 count=0\n"
  "hart=4 count=0\n" "hart=5 count=0\n" "hart=6 count=0\n" "hart=7 count=0\n";
 return bytes==sizeof(expected)-1&&!memcmp(data,expected,bytes);
}
static int producer_read_empty(void) {
 char data[512];size_t used=0;
 int fd=open("/sys/kernel/debug/xr_npu_producer/snapshot",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
 if(fd<0)return 0;
 struct stat st;
 int valid=!fstat(fd,&st)&&S_ISREG(st.st_mode)&&st.st_uid==0&&(st.st_mode&0777)==0400;
 while(valid&&used<sizeof(data)) {
  ssize_t n=read(fd,data+used,sizeof(data)-used);
  if(n<0&&errno==EINTR)continue;
  if(n<0){valid=0;break;}
  if(!n)break;
  used+=(size_t)n;
 }
 if(close(fd))valid=0;
 return valid&&producer_empty(data,used);
}
static int producer_preflight(void) {
 pid_t child=fork();
 if(child<0)return 0;
 if(!child) {
  close(journal);
  signal(SIGALRM,SIG_DFL);alarm(2);
  _exit(producer_read_empty()?0:1);
 }
 uint64_t start=now_ms();
 if(start==UINT64_MAX){kill(child,SIGKILL);return 0;}
 int status=0;
 while(now_ms()-start<2500) {
  pid_t result=waitpid(child,&status,WNOHANG);
  if(result==child)return WIFEXITED(status)&&WEXITSTATUS(status)==0;
  if(result<0&&errno!=EINTR)break;
  struct timespec delay={.tv_nsec=20000000};nanosleep(&delay,NULL);
 }
 /* Never wait synchronously for a task stuck in a driver read. The independent
  * recovery process remains in control even when SIGKILL is merely pending. */
 kill(child,SIGKILL);
 waitpid(child,&status,WNOHANG);
 return 0;
}

int main(int argc,char **argv) {
 (void)argv;if(argc!=1||geteuid()!=0)return 2;
 char value[128];if(read_file("/proc/sys/kernel/random/boot_id",value,sizeof(value))!=37)return 2;
 value[36]=0;if(!uuid(value))return 2;strcpy(boot,value);
 snprintf(record,sizeof(record),"/root/xr-diag-journal/%s",boot);
 /* No symlink traversal in the owned persistent journal prefix. */
 int root=open("/root",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(root<0)return 2;
 int store=openat(root,"xr-diag-journal",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);close(root);if(store<0)return 2;
 journal=openat(store,boot,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);close(store);if(journal<0)return 2;
 struct stat st;if(fstat(journal,&st)||st.st_uid!=0||(st.st_mode&0777)!=0700)return 2;
 if(read_file("/tmp/sysinfo/board_name",value,sizeof(value))<0||strcmp(value,"gemtek,xr1710g\n"))return reject("wrong-board");
 if(!absent("/etc/xr-npu-guarded.once")||!absent("/etc/xr-recovery.once")||
    !absent("/etc/xr1710g-npu-audit.once")||!absent("/etc/modules.d/00-xr1710g-npu-audit"))return reject("pending-request-or-override");
 if(!absent("/sys/module/mt76"))return reject("module-already-loaded");
 if(!ppe_off()||!guard_valid(120))return reject("guard-or-ppe-not-ready");
 if(absent("/sys/module/xr_npu_addresses"))return reject("address-observer-not-loaded");
 if(absent("/sys/module/xr_npu_producer"))return reject("producer-observer-not-loaded");
 if(!producer_preflight())return reject("producer-firmware-or-empty-trace-invalid");
 if(!guard_valid(120)||!ppe_off())return reject("guard-invalid-after-producer-preflight");
 if(write_note("activation-requested.json","volatile-one-boot-module-options"))return reject("cannot-record-request");
 char dir[]="/tmp/xr-npu-modules.XXXXXX",path[PATH_MAX];if(!mkdtemp(dir))return reject("volatile-directory-failed");
 snprintf(path,sizeof(path),"%s/00-mt76",dir);
 int fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
 const char *options="mt76 npu_enable=1 npu_rx_audit=0 npu_txfree_chain_verify=0\n";
 int okay=fd>=0&&write(fd,options,strlen(options))==(ssize_t)strlen(options);
 if(fd>=0)close(fd);
 if(!okay){unlink(path);rmdir(dir);return reject("volatile-options-failed");}
 char directory[PATH_MAX];snprintf(directory,sizeof(directory),"%s/",dir);
 pid_t child=fork();
 if(!child){execl("/sbin/kmodloader","kmodloader",directory,(char *)NULL);_exit(127);}
 uint64_t end=now_ms()+10000;int status=0,finished=0;
 if(child>0)while(now_ms()<end&&guard_valid(30)) {
  pid_t result=waitpid(child,&status,WNOHANG);
  if(result==child){finished=1;break;}
  if(result<0&&errno!=EINTR)break;
  struct timespec t={.tv_nsec=100000000};nanosleep(&t,NULL);
 }
 if(child>0&&!finished)kill(child,SIGKILL);
 unlink(path);rmdir(dir);
 if(!finished||!WIFEXITED(status)||WEXITSTATUS(status))return reject("loader-failed-or-guard-invalid");
 if(!guard_valid(30)||!ppe_off()||!parameter_is("npu_enable",'Y')||!parameter_is("npu_rx_audit",'N')||!parameter_is("npu_txfree_chain_verify",'N'))return reject("actual-parameters-mismatch");
 if(write_note("module-enabled.json","NPU-boot-parameter-verified-driver-probe-pending"))return reject("cannot-record-parameters");
 return 0;
}
