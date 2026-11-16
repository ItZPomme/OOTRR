#include "lib.hpp"
#include "nn/os/os_thread_api.hpp"
#include "coords.hpp"
#include "coords_config.hpp"

/* Player position in the emulator log, to identify actors (chests, scrubs...) of a map.
 *
 * The game's SeqGetPlayerPos node (execution 0x32ed7a0) copies the player position from the object pointed to by the
 * global at 0x4e7cfa8: three floats at +0x590 / +0x594 / +0x598 (same units as the maps' Translate). A thread of ours
 * reads them every 250 ms and writes "OoTRR: position x y z" once Link has stood still for one second, at least 1 unit
 * away from the last logged position: one line per stop, nothing while running around. Test mods built with
 * `menutest --live-coords` (kLive) log every tick instead, as soon as Link moved 0.3 unit. `python -m ootrr.tools.coords`
 * reads these lines and names the nearest actors. Address and units: verified in the code, to validate in game. */

namespace ootrr::coords {
namespace {

constexpr ptrdiff_t kPlayerHolder = 0x4e7cfa8;  // global: pointer to the object that holds the player position
constexpr ptrdiff_t kPlayerPos = 0x590;          // three floats x, y, z
constexpr s64 kPeriodMs = 250;
constexpr int kStillTicks = 4;                   // 4 x 250 ms = one second without moving
constexpr float kStillDistance = 0.05f;
constexpr float kNewDistance = 1.0f;
constexpr float kLiveDistance = 0.3f;

alignas(0x1000) u8 g_stack[0x4000];
alignas(16) u8 g_thread[0x200];  // nn::os::ThreadType (0x1c0 bytes in the SDK)

void Log(const char* text) {
    size_t n = 0;
    while (text[n]) n++;
    svcOutputDebugString(text, n);
}

// "-1234.5": one decimal is enough to compare with the maps (lookup rounds to 0.1)
size_t PutFloat(char* out, float value) {
    size_t n = 0;
    if (value < 0) {
        out[n++] = '-';
        value = -value;
    }
    s64 tenths = static_cast<s64>(value * 10.0f + 0.5f);
    char digits[24];
    int d = 0;
    s64 whole = tenths / 10;
    do {
        digits[d++] = static_cast<char>('0' + whole % 10);
        whole /= 10;
    } while (whole && d < 20);
    while (d) out[n++] = digits[--d];
    out[n++] = '.';
    out[n++] = static_cast<char>('0' + tenths % 10);
    return n;
}

bool Finite(float v) { return v == v && v < 1.0e7f && v > -1.0e7f; }

float Distance2(const float* a, const float* b) {
    float dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2];
    return dx * dx + dy * dy + dz * dz;
}

bool ReadPosition(float* out) {
    uintptr_t holder = *reinterpret_cast<uintptr_t*>(exl::util::modules::GetTargetStart() + kPlayerHolder);
    if (!holder) return false;
    const float* pos = reinterpret_cast<const float*>(holder + kPlayerPos);
    for (int i = 0; i < 3; i++) {
        out[i] = pos[i];
        if (!Finite(out[i])) return false;
    }
    return true;
}

void Thread(void*) {
    float last[3] = {}, logged[3] = {};
    bool have_last = false, have_logged = false;
    int still = 0;
    while (true) {
        nn::os::SleepThread(nn::TimeSpan::FromMilliSeconds(kPeriodMs));
        float pos[3];
        if (!ReadPosition(pos)) {
            have_last = false;
            continue;
        }
        still = have_last && Distance2(pos, last) < kStillDistance * kStillDistance ? still + 1 : 0;
        last[0] = pos[0];
        last[1] = pos[1];
        last[2] = pos[2];
        have_last = true;
        if (kLive) {
            if (have_logged && Distance2(pos, logged) < kLiveDistance * kLiveDistance) continue;
        } else {
            if (still != kStillTicks) continue;
            if (have_logged && Distance2(pos, logged) < kNewDistance * kNewDistance) continue;
        }
        char buf[96];
        size_t n = 0;
        for (const char* p = "OoTRR: position"; *p; p++) buf[n++] = *p;
        for (int i = 0; i < 3; i++) {
            buf[n++] = ' ';
            n += PutFloat(buf + n, pos[i]);
        }
        buf[n] = 0;
        Log(buf);
        logged[0] = pos[0];
        logged[1] = pos[1];
        logged[2] = pos[2];
        have_logged = true;
    }
}

}  // namespace

void Start() {
    auto* thread = reinterpret_cast<nn::os::ThreadType*>(g_thread);
    if (nn::os::CreateThread(thread, Thread, nullptr, g_stack, sizeof(g_stack), 30) != 0) {
        Log("OoTRR: position thread not created");
        return;
    }
    nn::os::StartThread(thread);
    Log("OoTRR: position thread started");
}

}  // namespace ootrr::coords
