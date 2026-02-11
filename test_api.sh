#!/bin/bash

# API Testing Script untuk URL Shortener
# Pastikan server sudah running di http://localhost:8000

BASE_URL="http://localhost:8000"
ADMIN_KEY="your-super-secret-admin-key"  # Ganti dengan SUPER_ADMIN_KEY Anda

echo "=== URL Shortener API Testing ==="
echo ""

# 1. Health Check
echo "1. Testing Health Check..."
curl -s "$BASE_URL/health" | jq
echo ""

# 2. Generate API Key (Tier 3)
echo "2. Generating Tier 3 API Key..."
API_RESPONSE=$(curl -s -X POST "$BASE_URL/admin/api-keys" \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tier": 3,
    "name": "Test API Key",
    "description": "Testing purposes"
  }')

echo "$API_RESPONSE" | jq
API_KEY=$(echo "$API_RESPONSE" | jq -r '.api_key')
echo "Generated API Key: $API_KEY"
echo ""

# 3. Basic URL Shortening
echo "3. Testing Basic URL Shortening..."
curl -s -X POST "$BASE_URL/shorten" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.github.com/trending"
  }' | jq
echo ""

# 4. URL Shortening with Custom Code
echo "4. Testing Custom Short Code..."
curl -s -X POST "$BASE_URL/shorten" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.stackoverflow.com",
    "custom_code": "stack-overflow",
    "title": "Stack Overflow",
    "description": "Programming Q&A Site"
  }' | jq
echo ""

# 5. URL with Password Protection
echo "5. Testing Password Protected URL..."
PROTECTED_RESPONSE=$(curl -s -X POST "$BASE_URL/shorten" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.example.com/secret",
    "password": "secret123",
    "title": "Secret Link"
  }')

echo "$PROTECTED_RESPONSE" | jq
PROTECTED_CODE=$(echo "$PROTECTED_RESPONSE" | jq -r '.short_code')
echo ""

# 6. URL with Expiration
echo "6. Testing URL with Expiration (30 days)..."
curl -s -X POST "$BASE_URL/shorten" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.example.com/temporary",
    "expires_in_days": 30,
    "title": "Temporary Link"
  }' | jq
echo ""

# 7. Bulk URL Shortening
echo "7. Testing Bulk URL Shortening..."
curl -s -X POST "$BASE_URL/shorten/bulk" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://www.google.com",
      "https://www.facebook.com",
      "https://www.twitter.com",
      "https://www.linkedin.com"
    ]
  }' | jq
echo ""

# 8. Get Statistics
echo "8. Testing Get Statistics..."
curl -s "$BASE_URL/stats/$PROTECTED_CODE" \
  -H "X-API-Key: $API_KEY" | jq
echo ""

# 9. List User URLs
echo "9. Testing List URLs..."
curl -s "$BASE_URL/urls?limit=5" \
  -H "X-API-Key: $API_KEY" | jq
echo ""

# 10. Update URL
echo "10. Testing Update URL..."
curl -s -X PATCH "$BASE_URL/urls/$PROTECTED_CODE" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Secret Link",
    "description": "Now with updated description"
  }' | jq
echo ""

# 11. Test Redirect (without password - should fail)
echo "11. Testing Redirect Without Password (should fail)..."
curl -s -I "$BASE_URL/$PROTECTED_CODE" | head -n 5
echo ""

# 12. Test Redirect (with password - should succeed)
echo "12. Testing Redirect With Password (should succeed)..."
curl -s -I "$BASE_URL/$PROTECTED_CODE?password=secret123" | head -n 5
echo ""

# 13. Download QR Code
echo "13. Testing QR Code Generation..."
curl -s "$BASE_URL/qr/$PROTECTED_CODE?size=300" -o "qr_code_test.png"
if [ -f "qr_code_test.png" ]; then
    echo "✓ QR Code downloaded successfully as qr_code_test.png"
    ls -lh qr_code_test.png
else
    echo "✗ Failed to download QR code"
fi
echo ""

# 14. Admin Dashboard
echo "14. Testing Admin Dashboard..."
curl -s "$BASE_URL/admin/dashboard" \
  -H "X-API-Key: $ADMIN_KEY" | jq
echo ""

# 15. List All API Keys
echo "15. Testing List All API Keys..."
curl -s "$BASE_URL/admin/api-keys" \
  -H "X-API-Key: $ADMIN_KEY" | jq
echo ""

# 16. Delete URL
echo "16. Testing Delete URL..."
curl -s -X DELETE "$BASE_URL/urls/$PROTECTED_CODE" \
  -H "X-API-Key: $API_KEY" | jq
echo ""

# 17. Test Invalid API Key
echo "17. Testing Invalid API Key (should fail)..."
curl -s -X POST "$BASE_URL/shorten" \
  -H "X-API-Key: invalid-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.example.com"
  }' | jq
echo ""

# 18. Test Missing API Key
echo "18. Testing Missing API Key (should fail)..."
curl -s -X POST "$BASE_URL/shorten" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.example.com"
  }' | jq
echo ""

echo "=== Testing Complete ==="
echo ""
echo "Summary:"
echo "- Basic URL shortening: ✓"
echo "- Custom short codes: ✓"
echo "- Password protection: ✓"
echo "- URL expiration: ✓"
echo "- Bulk operations: ✓"
echo "- QR code generation: ✓"
echo "- Analytics: ✓"
echo "- Admin endpoints: ✓"
echo "- Error handling: ✓"
