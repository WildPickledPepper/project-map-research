#pragma once
namespace neutral_effects {
struct State { int value; };
void write(State& state, int input);
int read(const State& state);
State& borrow(State& state);
State copy(State state);
void write_global(int input);
int read_global();
State& select(State& first, State& second, bool use_first);
using Callback = int (*)(State&);
int through_callback(State& state, Callback callback);
}
