def calculate_bmi(height_cm: float, weight_kg: float) -> float:
    """根據身高 (公分) 與體重 (公斤) 計算 BMI"""
    height_m = height_cm / 100
    return weight_kg / (height_m ** 2)

def get_bmi_category(bmi: float) -> str:
    """依台灣衛福部標準判斷體位"""
    if bmi < 18.5:
        return "體重過輕"
    elif 18.5 <= bmi < 24:
        return "健康體位（正常）"
    elif 24 <= bmi < 27:
        return "過重"
    elif 27 <= bmi < 30:
        return "輕度肥胖"
    elif 30 <= bmi < 35:
        return "中度肥胖"
    else:
        return "重度肥胖"

def main():
    print("=== BMI 健康計算機 ===")
    try:
        height = float(input("請輸入身高 (公分 cm): "))
        weight = float(input("請輸入體重 (公斤 kg): "))

        bmi = calculate_bmi(height, weight)
        category = get_bmi_category(bmi)

        print("\n--- 計算結果 ---")
        print(f"您的 BMI 為：{bmi:.2f}")
        print(f"體位評估結果：{category}")
    except ValueError:
        print("請輸入有效的數字！")

if __name__ == "__main__":
    main()
