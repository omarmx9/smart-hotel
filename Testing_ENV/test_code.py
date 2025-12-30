"""
Simple test script for Layer 4 - Document Filling
Tests PDF overlay with predefined MRZ data
"""
import logging
from layer4_document_filling import DocumentFiller

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Test MRZ data - simulating extracted passport data
test_mrz_data = {
    "mrz_type": "TD3",
    "document_code": "P",
    "issuer_code": "EGY",
    "surname": "ABADY",
    "given_name": "MANSOUR FOUAD POHARED ELSHAHIR",
    "document_number": "A04288942",
    "document_number_checkdigit": "7",
    "nationality_code": "EGY",
    "birth_date": "1975-01-21",
    "birth_date_checkdigit": "8",
    "sex": "M",
    "expiry_date": "2030-12-03",
    "expiry_date_checkdigit": "9",
    "optional_data": "",
    "optional_data_checkdigit": "0",
    "final_checkdigit": "6",
    "status": "SUCCESS"
}

def test_document_filling():
    """Test the document filling with predefined MRZ data"""
    print("\n" + "="*60)
    print("LAYER 4 - DOCUMENT FILLING TEST")
    print("="*60)
    
    try:
        # Initialize document filler
        print("\n[1] Initializing DocumentFiller...")
        filler = DocumentFiller(
            template_path="templates/DWA_Registration_Card.pdf",
            output_dir="filled_documents"
        )
        print("✓ DocumentFiller initialized")
        
        # Fill registration card
        print("\n[2] Filling registration card with test MRZ data...")
        print(f"    Name: {test_mrz_data['given_name']} {test_mrz_data['surname']}")
        print(f"    Nationality: {test_mrz_data['nationality_code']}")
        print(f"    Passport: {test_mrz_data['document_number']}")
        
        result = filler.fill_registration_card(test_mrz_data)
        
        print("\n[3] ✓ Success!")
        print(f"    Output file: {result['output_filename']}")
        print(f"    Full path: {result['output_path']}")
        print(f"    Timestamp: {result['timestamp']}")
        
        print("\n" + "="*60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*60)
        print(f"\nCheck the file: {result['output_path']}")
        print("Verify that MRZ data is correctly positioned over the template fields.")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        print("\n" + "="*60)
        print("TEST FAILED")
        print("="*60)
        return False


def test_multiple_samples():
    """Test with multiple different passport samples"""
    print("\n" + "="*60)
    print("TESTING MULTIPLE SAMPLES")
    print("="*60)
    
    samples = [
        {
            "surname": "SMITH",
            "given_name": "JOHN MICHAEL",
            "nationality_code": "USA",
            "document_number": "123456789",
            "birth_date": "1990-05-15",
            "expiry_date": "2028-05-15",
            "issuer_code": "USA"
        },
        {
            "surname": "MUELLER",
            "given_name": "ANNA",
            "nationality_code": "DEU",
            "document_number": "C01234567",
            "birth_date": "1985-12-20",
            "expiry_date": "2027-12-20",
            "issuer_code": "DEU"
        },
        {
            "surname": "TANAKA",
            "given_name": "HIROSHI",
            "nationality_code": "JPN",
            "document_number": "TK1234567",
            "birth_date": "1988-03-10",
            "expiry_date": "2029-03-10",
            "issuer_code": "JPN"
        }
    ]
    
    filler = DocumentFiller(
        template_path="templates/DWA_Registration_Card.pdf",
        output_dir="filled_documents"
    )
    
    for i, sample in enumerate(samples, 1):
        print(f"\n[Sample {i}] {sample['given_name']} {sample['surname']}")
        try:
            result = filler.fill_registration_card(sample)
            print(f"  ✓ {result['output_filename']}")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    # Run basic test
    success = test_document_filling()
    
    # Optionally run multiple samples test
    if success:
        choice = input("\nTest with multiple samples? (y/n): ").lower()
        if choice == 'y':
            test_multiple_samples()