void sink(int value);
int forward(int value) { return value; }
struct Cell {
    int value;
    const int& borrow() const { return value; }
    int copy() const { return value; }
};
void regular(int input) { int result = forward(input); sink(result); }
void member(int input) { Cell first{}; first.value = input; sink(first.value); }
void isolated(int input) { Cell first{}, second{}; first.value = input; sink(second.value); }
void after_copy(int input) { Cell first{}; first.value = 0; auto copy = first; first.value = input; sink(copy.value); }
void borrowed(int input) { Cell first{}; const Cell& alias = first; first.value = input; sink(alias.value); }
void getter(int input) { Cell first{}; first.value = input; sink(first.borrow()); }
