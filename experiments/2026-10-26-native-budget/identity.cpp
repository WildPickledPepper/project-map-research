// Frozen identity check: shared pointee versus an independent global object.
extern "C" {
int first_object;
int second_object;
int* first_alias = &first_object;
int* second_alias = &first_object;
int* isolated_alias = &second_object;
}
