import re

def detect_fake_review(review_text):
    """
    A simple function to simulate AI-based fake review detection.
    This is for local testing only.
    """
    review_text_lower = review_text.lower()
    suspicious_phrases = [
        "out of this world",
        "amazing experience",
        "free drink",
        "promotion",
        "coupon"
    ]
    
    for phrase in suspicious_phrases:
        if re.search(r'\b' + re.escape(phrase) + r'\b', review_text_lower):
            return "Fake"
            
    return "Genuine"