#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <unistd.h>

static int fault_for(int fd) {
    const char *root = getenv("COOLDOWN_FAULT_ROOT");
    const char *arm = getenv("COOLDOWN_FAULT_ARM");
    const char *mode = getenv("COOLDOWN_FAULT_MODE");
    if (!root || !arm || !mode || access(arm, F_OK) != 0) return 0;
    char link[64], path[4096];
    /* Descriptor paths are bounded decimal integers; no payload is logged. */
    int length = snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
    if (length <= 0 || (size_t)length >= sizeof(link)) return 0;
    ssize_t size = readlink(link, path, sizeof(path) - 1);
    if (size <= 0) return 0;
    path[size] = 0;
    size_t prefix = strlen(root);
    if (strncmp(path, root, prefix) != 0 || path[prefix] != '/') return 0;
    int kind = !strcmp(mode, "enospc") ? 1 : !strcmp(mode, "eio") ? 2 :
               !strcmp(mode, "torn-write") ? 3 : 0;
    if (!kind) return 0;
    const char *hit = getenv("COOLDOWN_FAULT_HIT");
    if (hit) {
        int marker = (int)syscall(SYS_openat, AT_FDCWD, hit, O_WRONLY|O_CREAT|O_APPEND, 0600);
        if (marker >= 0) {
            syscall(SYS_write, marker, "hit\n", 4);
            syscall(SYS_close, marker);
        }
    }
    errno = kind == 1 ? ENOSPC : EIO;
    return kind;
}
static void die(void) {
    syscall(SYS_kill, getpid(), SIGKILL);
    _exit(137);
}
ssize_t pwrite64(int fd, const void *buf, size_t count, off64_t offset) {
    int kind = fault_for(fd);
    if (kind == 3) {
        syscall(SYS_pwrite64, fd, buf, count > 1 ? count / 2 : count, offset);
        syscall(SYS_fsync, fd);
        die();
    }
    if (kind) return -1;
    return syscall(SYS_pwrite64, fd, buf, count, offset);
}
ssize_t pwrite(int fd, const void *buf, size_t count, off_t offset) {
    return pwrite64(fd, buf, count, (off64_t)offset);
}
ssize_t write(int fd, const void *buf, size_t count) {
    int kind = fault_for(fd);
    if (kind == 3) {
        syscall(SYS_write, fd, buf, count > 1 ? count / 2 : count);
        syscall(SYS_fsync, fd);
        die();
    }
    if (kind) return -1;
    return syscall(SYS_write, fd, buf, count);
}
ssize_t writev(int fd, const struct iovec *iov, int count) {
    int kind = fault_for(fd);
    if (kind == 3 && count > 0) {
        syscall(SYS_write, fd, iov[0].iov_base, iov[0].iov_len / 2);
        syscall(SYS_fsync, fd);
        die();
    }
    if (kind) return -1;
    return syscall(SYS_writev, fd, iov, count);
}
