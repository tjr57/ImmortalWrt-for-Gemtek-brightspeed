/* Shared bounded diagnostic window. No running deadline extension. */
#ifndef XR_DIAG_LIMITS_H
#define XR_DIAG_LIMITS_H
#include <stdint.h>
#define XR_DIAG_MAX_SECONDS 480U
#define XR_DIAG_CAPTURE_TAIL_SECONDS 15U
_Static_assert(XR_DIAG_MAX_SECONDS + XR_DIAG_CAPTURE_TAIL_SECONDS <= 600U,
               "recovery duration must fit the unchanged collector bound");
static inline int xr_diag_duration_valid(unsigned long seconds) {
 return seconds >= 15 && seconds <= XR_DIAG_MAX_SECONDS;
}
static inline int xr_diag_window_valid(uint64_t now, int64_t expires,
                                     unsigned minimum_seconds) {
 return expires >= 0 && (uint64_t)expires >= now &&
        (uint64_t)expires - now >= (uint64_t)minimum_seconds * 1000 &&
        (uint64_t)expires - now <= (uint64_t)XR_DIAG_MAX_SECONDS * 1000;
}
#endif
