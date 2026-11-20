int main(void) {
    int a[5] = {5, -2, 4, 1, 4};
    int end = 4;

    while (end > 0) {
        int j = 0;
        while (j < end) {
            if (a[j] > a[j + 1]) {
                int tmp = a[j];
                a[j] = a[j + 1];
                a[j + 1] = tmp;
            }
            j = j + 1;
        }
        end = end - 1;
    }
    return 0;
}
