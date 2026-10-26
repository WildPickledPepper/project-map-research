#include "effects.hpp"
namespace neutral_effects {
int shared_value;
void write(State& state, int input) { state.value = input; }
int read(const State& state) { return state.value; }
State& borrow(State& state) { return state; }
State copy(State state) { return state; }
void write_global(int input) { shared_value = input; }
int read_global() { return shared_value; }
State& select(State& first, State& second, bool use_first) { return use_first ? first : second; }
int through_callback(State& state, Callback callback) { return callback(state); }
}
