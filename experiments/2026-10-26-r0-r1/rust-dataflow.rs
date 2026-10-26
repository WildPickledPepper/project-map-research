//! Independent native-provider admission inputs. No historical issue material.
#[derive(Clone,Copy)]
pub struct Cell { pub value:i32 }
#[inline(never)]
pub fn forward(value:i32)->i32 {value}
#[inline(never)]
pub fn regular(input:i32)->i32 {forward(input)}
pub fn member(input:i32)->i32 {let mut first=Cell{value:0};first.value=input;first.value}
pub fn isolated(input:i32)->i32 {let mut first=Cell{value:0};let second=Cell{value:0};first.value=input;second.value}
pub fn after_copy(input:i32)->i32 {let mut first=Cell{value:0};let copy=first;first.value=input;copy.value}
pub fn borrowed(input:i32)->i32 {let mut first=Cell{value:0};let alias=&mut first;alias.value=input;first.value}
#[inline(never)]
pub fn constant(_ignored:i32)->i32 {0}
pub fn through_ignored(input:i32)->i32 {constant(input)}
pub fn borrow_field(cell:&Cell)->&i32 {&cell.value}
pub fn borrow_identity(cell:&Cell)->&Cell {cell}
#[cfg(test)]
mod tests {
    #[test]
    fn independent_values_and_borrow_identity() {
        for input in [17,83] {
            for function in [super::regular,super::member,super::borrowed] {assert_eq!(function(input),input);}
            for function in [super::isolated,super::after_copy,super::through_ignored] {assert_eq!(function(input),0);}
            let cell=super::Cell{value:input};
            assert!(std::ptr::eq(super::borrow_field(&cell),&cell.value));
            assert!(std::ptr::eq(super::borrow_identity(&cell),&cell));
        }
    }
}
