-- Create WELCOME10 (10% discount)
INSERT INTO discount_codes (code, discount_percent, is_active, max_uses, current_uses, is_free_generation, free_generations_count, created_at, updated_at)
VALUES ('WELCOME10', 10, true, NULL, 0, false, NULL, NOW(), NOW())
ON CONFLICT (code) DO UPDATE SET is_active = true, updated_at = NOW();

-- Create SAVE20 (20% discount)
INSERT INTO discount_codes (code, discount_percent, is_active, max_uses, current_uses, is_free_generation, free_generations_count, created_at, updated_at)
VALUES ('SAVE20', 20, true, NULL, 0, false, NULL, NOW(), NOW())
ON CONFLICT (code) DO UPDATE SET is_active = true, updated_at = NOW();

-- Create BONUS30 (30% discount)
INSERT INTO discount_codes (code, discount_percent, is_active, max_uses, current_uses, is_free_generation, free_generations_count, created_at, updated_at)
VALUES ('BONUS30', 30, true, NULL, 0, false, NULL, NOW(), NOW())
ON CONFLICT (code) DO UPDATE SET is_active = true, updated_at = NOW();

-- Create FREE_ACCESS (unlimited free operations)
INSERT INTO discount_codes (code, discount_percent, is_active, max_uses, current_uses, is_free_generation, free_generations_count, created_at, updated_at)
VALUES ('FREE_ACCESS', 0, true, NULL, 0, false, NULL, NOW(), NOW())
ON CONFLICT (code) DO UPDATE SET is_active = true, updated_at = NOW();

-- Show all discount codes
SELECT code, discount_percent, is_active FROM discount_codes WHERE code IN ('WELCOME10', 'SAVE20', 'BONUS30', 'FREE_ACCESS') ORDER BY code;











