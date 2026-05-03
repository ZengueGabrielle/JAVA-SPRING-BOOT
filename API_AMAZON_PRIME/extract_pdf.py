import PyPDF2
import sys

def extract():
    try:
        reader = PyPDF2.PdfReader('c:/Users/ZNS_GABRIELLE/Desktop/FORMATION/Cours_Keyce_B2/Cours_Keyce_B2/SN2/Java_spring_boot/API_AMAZON_PRIME/cours_Developpement_API_REST[Bachelor2][Evaris Fomekong].pdf')
        text = ''.join(page.extract_text() for page in reader.pages)
        with open('extracted_text.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        print("Success")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract()
