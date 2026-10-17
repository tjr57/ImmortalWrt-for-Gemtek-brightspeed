// SPDX-License-Identifier: GPL-2.0-only
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>
#define FILEPATH "/sys/kernel/debug/xr_npu_producer/snapshot"
#define REQUIRE(x) do { if (!(x)) { fprintf(stderr,"XR_PRODUCER_FAIL line=%d errno=%d\n",__LINE__,errno);return 1;} } while(0)
static char buf[100000];
int main(int argc,char **argv)
{
 struct stat st;int fd,expected,status,rows=0;ssize_t n;size_t size=0;pid_t child;char *p;
 REQUIRE(argc==3);expected=atoi(argv[1]);fd=open(FILEPATH,O_RDONLY);REQUIRE(fd>=0);
 REQUIRE(fstat(fd,&st)==0 && (st.st_mode&0777)==0400);
 n=read(fd,buf,sizeof(buf)-1);
 if(expected){REQUIRE(n==-1 && errno==expected);REQUIRE(close(fd)==0);return 0;}
 REQUIRE(n>0);size=n;
 while((n=read(fd,buf+size,sizeof(buf)-1-size))>0){size+=n;REQUIRE(size<sizeof(buf)-1);}
 REQUIRE(n==0);buf[size]=0;
 REQUIRE(strstr(buf,"schema=2 atomic=0 source=producer-scalar record_words=12\n"));
 for(p=buf;(p=strstr(p," record="));p++)rows++;
 REQUIRE(rows==atoi(argv[2]));
 if(rows) REQUIRE(strstr(buf,"w3=300a005c w4=00000005") && strstr(buf,"w7=30010014"));
 REQUIRE(write(fd,"1",1)==-1 && errno==EBADF);
 REQUIRE(syscall(SYS_delete_module,"xr_npu_producer",O_NONBLOCK)==-1);
 REQUIRE(errno==EBUSY || errno==EWOULDBLOCK);
 REQUIRE(lseek(fd,0,SEEK_SET)==0 && read(fd,buf,sizeof(buf))>0);
 child=fork();REQUIRE(child>=0);
 if(!child){close(fd);if(setuid(65534))_exit(2);int f=open(FILEPATH,O_RDONLY);_exit(f==-1 && errno==EACCES?0:3);}
 REQUIRE(waitpid(child,&status,0)==child && WIFEXITED(status) && !WEXITSTATUS(status));
 REQUIRE(close(fd)==0);
 fd=open(FILEPATH,O_WRONLY);
 if(fd>=0){REQUIRE(write(fd,"1",1)==-1);REQUIRE(close(fd)==0);}
 printf("XR_PRODUCER_ROWS=%d BYTES=%zu\n",rows,size);return 0;
}
