#pragma once
#include_next <filesystem>
#include <chrono>
namespace std { namespace filesystem {
struct eval_clock128 {
 using rep=__int128;
 using period=file_time_type::duration::period;
 using duration=std::chrono::duration<rep,period>;
 using time_point=std::chrono::time_point<eval_clock128,duration>;
 static constexpr bool is_steady=false;
};
inline eval_clock128::time_point eval_last_write_time(const path& p,std::error_code& e) noexcept {
 const auto t=std::filesystem::last_write_time(p,e);
 return eval_clock128::time_point(eval_clock128::duration(static_cast<__int128>(t.time_since_epoch().count())));
}
inline eval_clock128::time_point eval_last_write_time(const path& p) {
 const auto t=std::filesystem::last_write_time(p);
 return eval_clock128::time_point(eval_clock128::duration(static_cast<__int128>(t.time_since_epoch().count())));
}
}}
#define last_write_time eval_last_write_time
