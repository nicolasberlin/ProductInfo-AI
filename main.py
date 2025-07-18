
from agent.parser import extract_text

def main():
    #product_name = input("Product name: ")
    #company_name = input("Company name: ")

    text = extract_text(r"C:\Users\geneb\Desktop\ProductInfo AI\data\Exam (1).pdf")
    print(text)

    with open("output.txt", "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()