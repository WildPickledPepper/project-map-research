#include "contracts.h"
namespace alpha {
bool Live::query(int key) { return key != 0; }
bool Live::query(const char* key) { return key != nullptr; }
}
