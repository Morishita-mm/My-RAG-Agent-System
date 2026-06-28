# dummy_target.py
def divide_numbers(a, b):
    # bが0のときにZeroDivisionErrorが発生するのを防ぐため、エラーハンドリングを追加
    try:
        return a / b
    except ZeroDivisionError as e:
        print(f"Error: {e}. Division by zero is not allowed.")
        return None

if __name__ == "__main__":
    divide_numbers(10, 0)
