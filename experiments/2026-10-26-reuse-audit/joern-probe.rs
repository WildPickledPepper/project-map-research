fn sink(value: i32) {}
fn forward(value: i32) -> i32 { value }
fn regular(input: i32) { let result = forward(input); sink(result); }
