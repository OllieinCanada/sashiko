#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

/* Process-local test shim. Monotonic clocks and the host clock stay real. */
static int controlled_seconds(time_t *seconds) {
    const char *path = getenv("SASHIKO_TEST_REALTIME_FILE");
    if (!path || !*path)
        return 0;
    int descriptor = (int)syscall(SYS_openat, AT_FDCWD, path, O_RDONLY, 0);
    if (descriptor < 0)
        return 0;
    char data[96];
    ssize_t size = syscall(SYS_read, descriptor, data, sizeof(data) - 1);
    (void)syscall(SYS_close, descriptor);
    if (size <= 0)
        return 0;
    data[size] = '\0';
    char *end = NULL;
    errno = 0;
    long long value = strtoll(data, &end, 10);
    if (errno || end == data || (*end && *end != '\n')
        || value < 0 || value > 253402300799LL)
        return 0;
    *seconds = (time_t)value;
    return 1;
}

int clock_gettime(clockid_t clock, struct timespec *result) {
    time_t seconds;
    if ((clock == CLOCK_REALTIME || clock == CLOCK_REALTIME_COARSE)
        && controlled_seconds(&seconds)) {
        result->tv_sec = seconds;
        result->tv_nsec = 0;
        return 0;
    }
    return (int)syscall(SYS_clock_gettime, clock, result);
}

int gettimeofday(struct timeval *result, void *timezone) {
    time_t seconds;
    if (controlled_seconds(&seconds)) {
        result->tv_sec = seconds;
        result->tv_usec = 0;
        (void)timezone;
        return 0;
    }
    return (int)syscall(SYS_gettimeofday, result, timezone);
}

time_t time(time_t *result) {
    time_t seconds;
    if (!controlled_seconds(&seconds))
        seconds = (time_t)syscall(SYS_time, NULL);
    if (result)
        *result = seconds;
    return seconds;
}
