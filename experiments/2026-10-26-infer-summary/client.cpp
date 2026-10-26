#include "effects.hpp"
namespace neutral_effects {
int direct(int input) { return input; }
int composed(int input) { State state{}; write(state, input); return read(borrow(state)); }
int isolated(int input) { State first{}, second{}; write(first, input); return read(second); }
int after_copy(int input) { State first{}; auto second = copy(first); write(first, input); return read(second); }
int through_global(int input) { write_global(input); return read_global(); }
int conditional(int input, bool enabled) { State first{}, second{}; write(select(first, second, enabled), input); return read(first); }
}
