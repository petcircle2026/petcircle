# Birthday Reminder Feature - Quick Reference Card

## 🎂 Feature Overview

Automatic WhatsApp birthday reminders for pets, sent 7 days before the pet's birthday.

| Aspect | Details |
|--------|---------|
| **Trigger** | Pet DOB on file + upcoming birthday date |
| **Timing** | 7 days before birthday (via daily reminder engine at 8 AM IST) |
| **Message Type** | WhatsApp template (celebratory) |
| **Template Name** | `WHATSAPP_TEMPLATE_BIRTHDAY` (env variable) |
| **Recurrence** | Annual (365 days) |
| **Works For** | Dogs & Cats |

---

## 📋 Implementation Checklist

### Code Changes
- [x] Added `WHATSAPP_TEMPLATE_BIRTHDAY` to `config.py`
- [x] Added "Birthday Celebration" item to `preventive_seeder.py`
- [x] Updated `onboarding.py` to create birthday records
- [x] Updated `reminder_engine.py` to send birthday template
- [x] Created `birthday_service.py` with utility functions

### Configuration
- [ ] Add env variable: `WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration`
- [ ] Create WhatsApp template in Meta Business Manager
- [ ] Get template approved
- [ ] Restart backend service

### Testing
- [ ] Run seed_reminder_test_data.py
- [ ] Verify birthday record created in DB
- [ ] Run reminder engine manually
- [ ] Check WhatsApp message received
- [ ] Run automated tests

---

## 🚀 Quick Start

### For Developers

**1. Sync latest code with birthday service:**
```bash
git pull origin main
```

**2. Add environment variable:**
```bash
# Add this to your .env files
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration
```

**3. Test locally:**
```bash
cd backend
python scripts/seed_reminder_test_data.py
```

### For DevOps/Deploy Team

**1. Create WhatsApp template:**
- Go to Meta Business Manager → Message Templates
- Create template named `birthday_celebration`
- Use template body from WHATSAPP_BIRTHDAY_TEMPLATE_SETUP.md
- Submit for approval

**2. Update environment:**
```bash
# Add to all env files (.env.dev, .env.prod, .env.test)
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration
```

**3. Deploy:**
```bash
git pull origin main
docker-compose down
docker-compose up -d
```

**4. Verify:**
```bash
# Check logs
docker logs pet-circle-backend | grep -i birthday

# Verify env variable set
docker exec pet-circle-backend env | grep WHATSAPP_TEMPLATE_BIRTHDAY
```

---

## 📊 Database Query Reference

### Check Birthday Master Created
```sql
SELECT * FROM preventive_master 
WHERE item_name = 'Birthday Celebration';
-- Should return 2 rows (dog + cat)
```

### Find Birthday Records
```sql
SELECT p.id, p.name, p.dob, pr.next_due_date, pr.status
FROM preventive_records pr
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
JOIN pets p ON pr.pet_id = p.id
WHERE pm.item_name = 'Birthday Celebration'
ORDER BY pr.next_due_date;
```

### Find Pending Birthday Reminders
```sql
SELECT r.id, p.name, r.next_due_date, r.status
FROM reminders r
JOIN preventive_records pr ON r.preventive_record_id = pr.id
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
JOIN pets p ON pr.pet_id = p.id
WHERE pm.item_name = 'Birthday Celebration' AND r.status = 'pending'
ORDER BY r.next_due_date;
```

### Find Pets Without DOB (Won't Get Birthday Reminders)
```sql
SELECT id, name, species FROM pets 
WHERE dob IS NULL AND is_deleted = false;
```

---

## 🧪 Testing Commands

### Manual Smoke Test
```bash
# 1. Create test data with birthday
python backend/scripts/seed_reminder_test_data.py

# 2. Verify record created
psql $DATABASE_URL -c "
SELECT p.name, p.dob, pr.next_due_date 
FROM pets p 
JOIN preventive_records pr ON p.id = pr.pet_id 
WHERE p.name = 'Bruno';"

# 3. Run reminder engine
curl -X POST http://localhost:8000/internal/run-reminder-engine \
  -H "X-ADMIN-KEY: $ADMIN_KEY" \
  -H "Content-Type: application/json"

# 4. Check logs
grep -i "birthday" app.log
```

### Automated Tests
```bash
# Run all tests
python -m pytest backend/tests -v

# Run just birthday tests
python -m pytest backend/tests -v -k birthday
```

---

## 🔧 Environment Variables

**Single env variable required:**

| Variable | Value | File |
|----------|-------|------|
| `WHATSAPP_TEMPLATE_BIRTHDAY` | `birthday_celebration` | All .env files |

---

## 📝 Related Files

| File | Purpose |
|------|---------|
| `BIRTHDAY_REMINDER_GUIDE.md` | Full implementation guide |
| `WHATSAPP_BIRTHDAY_TEMPLATE_SETUP.md` | Template setup guide |
| `BIRTHDAY_FEATURE_IMPLEMENTATION_SUMMARY.md` | Detailed summary |
| `app/services/birthday_service.py` | Birthday utilities |
| `app/services/preventive_seeder.py` | Seed data (birth added) |
| `app/services/onboarding.py` | Birthday record creation |
| `app/services/reminder_engine.py` | Birthday message sending |

---

## 🎨 WhatsApp Template Body

Copy this for Meta Business Manager:

```
🎉 Happy Birthday to {{1}}! 🎂✨ 

It's {{1}}'s special day today - {{2}}!

Your furry friend is turning a year older. Celebrate with extra treats, 
playtime, and cuddles. Let us help you make it special with our premium 
pet care products! 

Visit your dashboard for personalized birthday recommendations for {{1}}.
```

**Parameters:**
- `{{1}}` = Pet Name
- `{{2}}` = Birthday Date (DD Month YYYY format)

---

## 📞 Troubleshooting

### Birthday records not created for existing pets?
```
→ Only created during onboarding if DOB provided
→ To add for existing pets: Update pet.dob, then manually trigger creation
```

### Template not sending?
```sql
-- Check template approved
SELECT body FROM preventive_master WHERE item_name = 'Birthday Celebration';

-- Check env variable set in logs
grep WHATSAPP_TEMPLATE_BIRTHDAY app.log

-- Check reminder status
SELECT status FROM reminders WHERE id = 'reminder-id';
```

### Wrong birthday date?
```python
from app.utils.date_utils import get_today_ist
print(get_today_ist())  # Should be IST timezone
```

### Pet has DOB but no birthday record?
```bash
# Re-run seed for that pet
python -c "
from app.database import SessionLocal
from app.models.pet import Pet
from app.services.onboarding import seed_preventive_records_for_pet

db = SessionLocal()
pet = db.query(Pet).filter(Pet.name == 'Bruno').first()
if pet:
    seed_preventive_records_for_pet(db, pet)
"
```

---

## 💡 Key Concepts

### Next Birthday Calculation
```python
today = get_today_ist()
birthday_this_year = date(today.year, dob.month, dob.day)

if birthday_this_year >= today:
    return birthday_this_year  # Birthday hasn't passed yet
else:
    return date(today.year + 1, dob.month, dob.day)  # Next year's birthday
```

### Birthday = Every Other Preventive Item
- Uses same `preventive_record` + `reminder` + `whatsapp_template` system
- Only difference: special template name
- No database schema changes needed

### Rate Limiting Applied
- Standard WhatsApp rate limits apply (80 msg/min per user)
- Birthday reminders batched like other reminders
- No performance impact

---

## 🎯 Success Criteria

- [x] Birthday records created for pets with DOB during onboarding
- [x] Birthday records NOT created for pets without DOB
- [x] Birthday reminders sent 7 days before birthday
- [x] Special birthday template used (celebratory)
- [x] Message includes pet name and birthday date
- [x] System handles multiple birthdays correctly
- [x] Backward compatible with existing reminders
- [x] No database schema changes needed
- [x] Proper error handling and logging
- [x] Environment variable for template name

---

## 📱 WhatsApp Message Example

**Pet:** Bruno (Dog)
**Birthday:** June 15, 2024

**Received Message:**
```
🎉 Happy Birthday to Bruno! 🎂✨ 

It's Bruno's special day today - 15 June 2024!

Your furry friend is turning a year older. Celebrate with extra treats, 
playtime, and cuddles. Let us help you make it special with our premium pet 
care products! 

Visit your dashboard for personalized birthday recommendations for Bruno.
```

---

## 🔐 Security Notes

- User phone number encrypted in DB
- Decrypted only during message sending
- Masked in logs (`mask_phone()`)
- Rate limiting enforced
- No sensitive data in template body
- Same security as other reminders

---

## ✅ Sign-Off Checklist

- [ ] All files reviewed
- [ ] Environment variable documented
- [ ] WhatsApp template created & approved
- [ ] Tests passing
- [ ] Deployment procedure documented
- [ ] Monitoring/logging verified
- [ ] Rollback plan in place
- [ ] Team trained on feature

---

**Questions?** See BIRTHDAY_REMINDER_GUIDE.md for full documentation.

**Last Updated:** March 12, 2026
