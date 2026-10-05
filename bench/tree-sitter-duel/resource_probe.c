#define _GNU_SOURCE
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
/* Isolated native launcher avoids Python's inherited pre-exec RSS high-water
 * mark. This is whole-process Linux ru_maxrss, not allocated parser bytes. */
int main(int argc,char **argv) {
  if(argc<2){fputs("usage: resource_probe COMMAND [ARG...]\n",stderr);return 2;}
  pid_t pid=fork();
  if(pid<0){perror("fork");return 2;}
  if(pid==0){int fd=open("/dev/null",O_WRONLY);if(fd<0||dup2(fd,1)<0){perror("redirect");_exit(127);}close(fd);execvp(argv[1],argv+1);perror("execvp");_exit(127);}
  int status;struct rusage usage;pid_t got;
  do {got=wait4(pid,&status,0,&usage);} while(got<0&&errno==EINTR);
  if(got<0){perror("wait4");return 2;}
  int rc=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
  printf("{\"returncode\":%d,\"peak_rss_bytes\":%ld,\"user_cpu_s\":%.6f,\"system_cpu_s\":%.6f}\n",rc,usage.ru_maxrss*1024L,usage.ru_utime.tv_sec+usage.ru_utime.tv_usec/1e6,usage.ru_stime.tv_sec+usage.ru_stime.tv_usec/1e6);
  return rc;
}
