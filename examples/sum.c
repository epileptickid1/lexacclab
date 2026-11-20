int main(void) {
    int i = 1;
    int sum = 0;

    while (i <= 5) {
        if (i % 2 == 1) {
            sum = sum + i * i;
        } else {
            sum = sum - i;
        }
        i = i + 1;
    }
    return sum;
}
