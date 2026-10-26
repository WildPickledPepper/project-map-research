#include <cstdio>
#include "joern-probe.cpp"

static int observed;
void sink(int value) { observed = value; }

int main() {
    struct Check { const char* name; void (*run)(int); bool dependent; };
    const Check checks[] = {{"regular", regular, true}, {"member", member, true},
        {"isolated", isolated, false}, {"after_copy", after_copy, false},
        {"borrowed", borrowed, true}, {"getter", getter, true}};
    const int inputs[] = {17, 83};
    for (const auto& check : checks) {
        for (int input : inputs) {
            observed = -1;
            check.run(input);
            const int expected = check.dependent ? input : 0;
            std::printf("%s input=%d expected=%d actual=%d\n", check.name, input, expected, observed);
            if (observed != expected) return 1;
        }
    }
}
