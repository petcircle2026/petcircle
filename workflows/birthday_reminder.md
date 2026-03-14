# Birthday Reminder Feature - Implementation Guide

## Overview

The birthday reminder feature enables automated WhatsApp reminders to pet owners on their pet's birthday. Birthdays are tracked as part of the preventive record system, using the same reminder engine as other preventive items.

**Key Features:**
- ✅ Automatic birthday reminders sent 7 days before and up to 7 days after the birthday
- ✅ Special birthday celebration WhatsApp template (different from regular reminders)
- ✅ Only created if pet has date of birth (DOB) on file
- ✅ Annual recurrence (365-day cycle)
- ✅ Works for both dogs and cats

---

## Architecture

### Data Model

**Preventive Master Entry:**
```
item_name: "Birthday Celebration"
category: "complete"
circle: "health"
species: "dog" | "cat"
recurrence_days: 365
reminder_before_days: 7      # Send 7 days before birthday
overdue_after_days: 7        # Mark overdue 7 days after birthday
medicine_dependent: false
```

### Flow Diagram

```
Pet Onboarding
    ↓
Pet.dob provided?
    ├── YES → Create PreventiveRecord with Birthday Celebration
    │         last_done_date = previous_year's birthday
    │         next_due_date = calculated upcoming birthday
    │
    └── NO → Skip Birthday Celebration record


Daily Reminder Engine (8 AM IST)
    ↓
Find all PreventiveRecords with status='upcoming' or 'overdue'
    ↓
Prev.item = "Birthday Celebration"? 
    ├── YES → Send WHATSAPP_TEMPLATE_BIRTHDAY with birthday emoji celebration
    │         Parameters: [pet_name, formatted_birthday_date]
    │
    └── NO → Send standard WHATSAPP_TEMPLATE_REMINDER or WHATSAPP_TEMPLATE_OVERDUE
```

---

## WhatsApp Template Setup

### 1. Create WhatsApp Business Template

Create a new WhatsApp template in your Meta Business Account:

**Template Name:** `birthday_celebration` (or custom name in `.env`)

**Template Language:** English

**Message Category:** Marketing / Transactional (choose based on your use case)

**Template Body Example:**

```
🎉 Happy Birthday to {{1}}! 🎂✨ 

It's {{1}}'s special day today - {{2}}!

Your furry friend is turning a year older. Celebrate with extra treats, playtime, and cuddles. Let us help you make it special with our premium pet care products! 

Visit your dashboard for personalized birthday recommendations for {{1}}.
```

**Template Parameters:**
1. `{{1}}` - Pet name (e.g., "Bruno", "Whiskers")
2. `{{2}}` - Formatted birthday date (e.g., "06 June 2024")

### 2. Add Footer (Optional)

Add a footer with your business information or call-to-action:

```
For more information, visit your PetCircle dashboard.
```

### 3. Media (Optional)

You can add a birthday-themed image or emoji-rich header to make it more celebratory:
- Header Type: Text with emojis
- Example: "🎉 Birthday Celebration 🎂"

---

## Configuration

### Environment Variables

Add the birthday template name to your `.env` files:

```bash
# .env.development
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration

# .env.production
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration
```

The template name must match exactly what you created in Meta Business Manager.

### Backend Configuration

The configuration is automatically loaded via `app/config.py`:

```python
class Settings(BaseSettings):
    WHATSAPP_TEMPLATE_BIRTHDAY: str  # Added in config.py
```

No additional code changes needed for configuration.

---

## Code Implementation Details

### 1. Birthday Service (`app/services/birthday_service.py`)

Provides utility functions for birthday calculations:

```python
def calculate_next_birthday(dob: date) -> date:
    """Calculate next birthday from DOB, accounting for whether it's passed this year."""
    
def create_birthday_record(db: Session, pet: Pet) -> PreventiveRecord | None:
    """Create initial birthday preventive record during pet onboarding."""
    
async def send_birthday_message(...) -> dict | None:
    """Send special birthday celebration template."""
```

### 2. Preventive Seeder Update (`app/services/preventive_seeder.py`)

Added Birthday Celebration to the seed data:

```python
# Birthday Celebration (365-day annual event)
{
    "item_name": "Birthday Celebration",
    "category": "complete",
    "circle": "health",
    "species": "dog",  # Also added for "cat"
    "recurrence_days": 365,
    "medicine_dependent": False,
    "reminder_before_days": 7,   # Remind 7 days before
    "overdue_after_days": 7,     # Overdue 7 days after
},
```

### 3. Onboarding Integration (`app/services/onboarding.py`)

Updated `seed_preventive_records_for_pet()` to handle birthdays specially:

```python
if master.item_name == "Birthday Celebration":
    if not pet.dob:
        # Skip if no DOB
        continue
    
    # Calculate next birthday from DOB
    next_birthday = calculate_next_birthday(pet.dob)
    previous_birthday = date(next_birthday.year - 1, pet.dob.month, pet.dob.day)
    
    record = PreventiveRecord(
        pet_id=pet.id,
        preventive_master_id=master.id,
        last_done_date=previous_birthday,
        next_due_date=next_birthday,
        status="upcoming" if next_birthday <= today else "up_to_date",
    )
else:
    # Standard preventive record
    record = PreventiveRecord(...)
```

### 4. Reminder Engine Update (`app/services/reminder_engine.py`)

Updated `send_pending_reminders()` to detect birthday items and use the birthday template:

```python
if master.item_name == "Birthday Celebration":
    coro = send_template_message(
        db=db,
        to_number=plaintext_mobile,
        template_name=settings.WHATSAPP_TEMPLATE_BIRTHDAY,
        parameters=[pet.name, format_date_for_user(reminder.next_due_date)],
    )
else:
    # Standard reminder/overdue message
    coro = send_reminder_message(...)
```

---

## Testing

### Manual Testing

#### 1. Seed Reminder Test Data

```bash
cd backend
python scripts/seed_reminder_test_data.py
```

This creates:
- Test user with phone: `+919095705762`
- Test pet "Bruno" (dog) with DOB: `2023-06-15`
- Birthday record with upcoming status

#### 2. Verify Birthday Record Created

```bash
psql your_database_url
SELECT * FROM preventive_records WHERE preventive_master_id IN (
    SELECT id FROM preventive_master WHERE item_name = 'Birthday Celebration'
);
```

Expected output:
```
pet_id: [pet-uuid]
last_done_date: 2023-06-15  (previous year)
next_due_date: 2024-06-15    (upcoming)
status: upcoming
```

#### 3. Run Reminder Engine

```bash
curl -X POST http://localhost:8000/internal/run-reminder-engine \
  -H "X-ADMIN-KEY: your-admin-key" \
  -H "Content-Type: application/json"
```

Check logs for:
```
Birthday record created for pet_id=...
Reminder created: record_id=..., next_due=2024-06-15, status=upcoming
Birthday template sent to +919095705762 for pet=Bruno on 15 June 2024
```

#### 4. Check WhatsApp Message

The user at `+919095705762` should receive:
```
🎉 Happy Birthday to Bruno! 🎂✨ 

It's Bruno's special day today - 15 Jun 2024!

Your furry friend is turning a year older. Celebrate with extra treats, 
playtime, and cuddles. Let us help you make it special with our premium 
pet care products!
```

### Automated Testing

Add to `backend/tests/test_reminders.py`:

```python
def test_birthday_reminder_created():
    """Verify birthday reminders are created for pets with DOB."""
    # Create pet with DOB
    pet = Pet(dob=date(2022, 3, 15), ...)
    db.add(pet)
    db.flush()
    
    # Seed birthdays
    seed_preventive_records_for_pet(db, pet)
    
    # Verify birthday record created
    birthday_record = db.query(PreventiveRecord).filter(
        PreventiveRecord.pet_id == pet.id,
        PreventiveRecord.preventive_master.has(
            PreventiveMaster.item_name == "Birthday Celebration"
        )
    ).first()
    
    assert birthday_record is not None
    assert birthday_record.next_due_date == date(2024, 3, 15)

def test_birthday_reminder_skipped_without_dob():
    """Verify birthday reminders are NOT created without DOB."""
    pet = Pet(dob=None, ...)  # No DOB
    db.add(pet)
    db.flush()
    
    seed_preventive_records_for_pet(db, pet)
    
    birthday_record = db.query(PreventiveRecord).filter(
        PreventiveRecord.pet_id == pet.id,
        PreventiveRecord.preventive_master.has(
            PreventiveMaster.item_name == "Birthday Celebration"
        )
    ).first()
    
    assert birthday_record is None

def test_birthday_template_sent():
    """Verify birthday template uses special WHATSAPP_TEMPLATE_BIRTHDAY."""
    # Create reminder for birthday record
    # Mock send_template_message
    # Run send_pending_reminders
    # Assert send_template_message called with WHATSAPP_TEMPLATE_BIRTHDAY
```

---

## Migration Guide

### For Existing Pets Without DOB

If you want to add birthday reminders to existing pets, you'll need to:

1. **Update pet records with DOB:**
   ```sql
   UPDATE pets SET dob = '2020-03-15' WHERE id = 'pet-uuid';
   ```

2. **Create birthday records:**
   ```python
   # Run this script once
   from app.services.birthday_service import create_birthday_record
   
   for pet in db.query(Pet).filter(Pet.dob.isnot(None)).all():
       create_birthday_record(db, pet)
   ```

3. **Verify creation:**
   ```bash
   SELECT COUNT(*) FROM preventive_records 
   WHERE preventive_master_id IN (
       SELECT id FROM preventive_master 
       WHERE item_name = 'Birthday Celebration'
   );
   ```

---

## WhatsApp Template Examples

### Example 1: Celebratory Style
```
🎉🎂🎊 Happy Birthday {{1}}! 🎂🎉🎊

Today marks another year of love, joy, and memorable moments with your 
furry friend!

Date: {{2}}

Celebrate with:
✨ Special treats & toys
✨ Extra cuddles & playtime  
✨ A visit to your dashboard for birthday recommendations

Your PetCircle family wishes {{1}} a purrfect day! 

Check out our birthday special offers on premium pet care products.
```

### Example 2: Professional Style
```
Happy Birthday {{1}}!

We're celebrating {{1}}'s birthday on {{2}}.

As {{1}} grows one year older, we're here to help with age-appropriate 
nutrition, healthcare, and wellness recommendations.

Visit your dashboard to view personalized birthday recommendations for {{1}}.

Best wishes from the PetCircle Team! 🐾
```

### Example 3: Fun & Playful
```
🐾 BIRTHDAY ALERT! 🐾

{{1}} is turning a year older today - {{2}}!

Time to:
🎉 Break out the treats
🎂 Plan the perfect play session
😄 Spoil them rotten

Visit PetCircle dashboard to find the perfect birthday gift and special 
birthday-month offers just for {{1}}!

Happy Birthday {{1}}! 🎈
```

---

## Troubleshooting

### Birthday Reminders Not Triggering

**Check 1: Preventive master seeded correctly**
```sql
SELECT * FROM preventive_master WHERE item_name = 'Birthday Celebration';
-- Should return 2 rows (dog + cat)
```

**Check 2: Pet has DOB**
```sql
SELECT id, name, dob, species FROM pets WHERE dob IS NOT NULL;
```

**Check 3: Birthday record created**
```sql
SELECT pr.id, p.name, p.dob, pr.next_due_date, pr.status 
FROM preventive_records pr
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
JOIN pets p ON pr.pet_id = p.id
WHERE pm.item_name = 'Birthday Celebration';
```

**Check 4: Reminder created and pending**
```sql
SELECT r.id, r.next_due_date, r.status
FROM reminders r
JOIN preventive_records pr ON r.preventive_record_id = pr.id
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
WHERE pm.item_name = 'Birthday Celebration' AND r.status = 'pending';
```

### Template Not Sending

**Check 1: Environment variable set**
```bash
echo $WHATSAPP_TEMPLATE_BIRTHDAY
# Should output the template name
```

**Check 2: Template approved in Meta Business Manager**
- Go to Meta Business Manager → WhatsApp → Message Templates
- Verify `birthday_celebration` template is in "APPROVED" status

**Check 3: Template name matches exactly**
- Env variable name should match Meta's template name exactly
- No extra spaces or incorrect casing

### Wrong Birthday Date Calculated

The birthday calculator uses timezone-aware date operations. Verify timezone:

```python
from app.utils.date_utils import get_today_ist
print(get_today_ist())  # Should output current date in Asia/Kolkata(IST)
```

---

## Future Enhancements

1. **Birthday Gift Recommendations**: Auto-suggest pet toys/treats based on age
2. **Birthday Photo Collection**: Allow users to upload birthday photos to dashboard
3. **Birthday Anniversary Tracker**: Show years celebrated with PetCircle
4. **Birthday Notifications**: Remind owners 30 days before (in addition to 7 days)
5. **Birthday Discount Codes**: Generate special discount codes on birthday month
6. **Interactive Birthday Buttons**: Let users RSVP or schedule vet checkups on birthday

---

## Related Documents

- [Reminder System Architecture](./REMINDER_SYSTEM_ANALYSIS.md)
- [Preventive Record System](./backend/app/models/preventive_record.py)
- [Onboarding Flow](./backend/app/services/onboarding.py)
- [WhatsApp Integration](./backend/app/services/whatsapp_sender.py)

# Birthday Reminder Feature - Setup Instructions

## ✅ What's Been Implemented

The complete backend for birthday reminders is ready. All code changes are done and error-free.

### Code Files Modified/Created:
- ✅ `backend/app/config.py` - Added `WHATSAPP_TEMPLATE_BIRTHDAY` env variable
- ✅ `backend/app/services/preventive_seeder.py` - Added "Birthday Celebration" item
- ✅ `backend/app/services/onboarding.py` - Birthday record creation logic
- ✅ `backend/app/services/reminder_engine.py` - Birthday template sending
- ✅ `backend/app/services/birthday_service.py` - Birthday utilities (NEW)
- ✅ Documentation files (4 guides)

---

## 🚀 What You Need to Do (3 Steps)

### STEP 1: Create WhatsApp Template (5 minutes)

1. Go to [Meta Business Manager](https://business.facebook.com)
2. Navigate to **WhatsApp** > **Message Templates** > **Create Template**
3. Fill in:
   - **Template Name:** `birthday_celebration`
   - **Category:** Marketing or Transactional
   - **Language:** English
   - **Message Body:**

```
🎉 Happy Birthday to {{1}}! 🎂✨ 

It's {{1}}'s special day today - {{2}}!

Your furry friend is turning a year older. Celebrate with extra treats, playtime, and cuddles. Let us help you make it special with our premium pet care products! 

Visit your dashboard for personalized birthday recommendations for {{1}}.
```

4. Click **Submit for Review**
5. Wait for approval (usually 1-2 hours, often immediate)

<img alt="WhatsApp Template" src="https://via.placeholder.com/600x400?text=WhatsApp+Template+Creation" />

---

### STEP 2: Update Environment Variables (2 minutes)

Add this line to ALL your `.env` files:

**`.env.development`**
```bash
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration
```

**`.env.production`**
```bash
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration
```

**`.env.test`**
```bash
WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration
```

---

### STEP 3: Deploy & Restart (5 minutes)

```bash
# 1. Pull latest code
git pull origin main

# 2. Restart backend service
docker-compose down
docker-compose up -d

# 3. Verify (check logs)
docker logs pet-circle-backend | grep -i birthday

# Expected log output:
# "Birthday template sent to +91... for pet=Bruno on 15 June 2024"
```

---

## 🧪 Testing (Before Going Live)

### Quick Smoke Test

```bash
# 1. Create test data
cd backend
python scripts/seed_reminder_test_data.py

# Expected output:
# Created pet "Bruno" with DOB 2023-06-15
# Seeded preventive records including Birthday Celebration

# 2. Check birthday record created
psql $DATABASE_URL << EOF
SELECT p.name, p.dob, pm.item_name, pr.next_due_date, pr.status
FROM pets p
JOIN preventive_records pr ON p.id = pr.pet_id
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
WHERE pm.item_name = 'Birthday Celebration';
EOF

# Expected: One row with Bruno, next_due_date = June 15 of this/next year

# 3. Run reminder engine
curl -X POST http://localhost:8000/internal/run-reminder-engine \
  -H "X-ADMIN-KEY: $ADMIN_KEY" \
  -H "Content-Type: application/json"

# Expected output (in logs):
# "Birthday template sent to +919095705762 for pet=Bruno on 15 June 2024"

# 4. Check the test user's WhatsApp
# Phone: +919095705762
# Should receive birthday message within seconds
```

---

## 📊 How It Works

```
On Pet Onboarding (if DOB provided):
  → Birthday record created with next_due_date = upcoming birthday

Every Day at 8 AM IST:
  → Reminder engine checks all preventive records
  → If Birthday Celebration is within 7 days → Creates reminder
  → If Birthday Celebration is within 7 days AFTER → Creates reminder (overdue)

Reminder Engine Sends Messages:
  → Detects "Birthday Celebration" item
  → Uses WHATSAPP_TEMPLATE_BIRTHDAY
  → Sends: [pet_name, birthday_date]

User Receives:
  → 🎉 Happy Birthday to Bruno! 🎂✨
     It's Bruno's special day today - 15 June 2024!
     ...
```

---

## 📋 Checklist for Deployment

- [ ] WhatsApp template created in Meta Business Manager
- [ ] Template status is "APPROVED" (check email)
- [ ] Env variable added to all `.env` files
- [ ] Code pulled from main branch
- [ ] Backend restarted
- [ ] Logs show birthday template loaded
- [ ] Smoke test completed successfully
- [ ] Test message received on +919095705762
- [ ] Team notified of new feature

---

## 🔍 Verification Queries

Run these SQL queries to verify everything is working:

### Check Birthday Master Item Exists
```sql
SELECT id, item_name, species, recurrence_days, reminder_before_days 
FROM preventive_master 
WHERE item_name = 'Birthday Celebration';
-- Should return 2 rows (dog + cat)
```

### Find All Birthday Records
```sql
SELECT p.id, p.name, p.dob, p.species, pr.id as record_id, 
       pr.next_due_date, pr.status, pr.created_at
FROM preventive_records pr
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
JOIN pets p ON pr.pet_id = p.id
WHERE pm.item_name = 'Birthday Celebration'
ORDER BY p.name;
```

### Find Pets WITHOUT DOB (Won't Get Reminders)
```sql
SELECT id, name, species, dob FROM pets 
WHERE dob IS NULL AND is_deleted = false;
-- Action: Update DOB for these pets if desired
```

### Find Pending Birthday Reminders
```sql
SELECT r.id, p.name, r.next_due_date, r.status, r.created_at
FROM reminders r
JOIN preventive_records pr ON r.preventive_record_id = pr.id
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
JOIN pets p ON pr.pet_id = p.id
WHERE pm.item_name = 'Birthday Celebration' AND r.status = 'pending'
ORDER BY r.next_due_date;
```

### Find Sent Birthday Reminders
```sql
SELECT r.id, p.name, r.next_due_date, r.status, r.sent_at
FROM reminders r
JOIN preventive_records pr ON r.preventive_record_id = pr.id
JOIN preventive_master pm ON pr.preventive_master_id = pm.id
JOIN pets p ON pr.pet_id = p.id
WHERE pm.item_name = 'Birthday Celebration' AND r.status = 'sent'
ORDER BY r.sent_at DESC
LIMIT 10;
```

## 🐛 Troubleshooting

### Problem: "Template not found" error in logs

**Solution:**
```bash
# 1. Verify template name in env
grep WHATSAPP_TEMPLATE_BIRTHDAY .env.*

# 2. Check template status in Meta Business Manager
# Should be "APPROVED", not "PENDING"

# 3. Restart backend to reload env
docker-compose down
docker-compose up -d
```

### Problem: No birthday reminders sent

**Check in order:**
1. Pet has DOB? → `SELECT dob FROM pets WHERE id = 'pet-id';`
2. Birthday record created? → Run query above
3. Birthday within 7 days? → Check next_due_date in database
4. Reminder created? → Check reminders table
5. Reminder sent? → Check logs for "Birthday template sent"

### Problem: Wrong birthday date in message

**Check timezone:**
```python
# SSH into backend
python -c "
from app.utils.date_utils import get_today_ist
print('Current date (IST):', get_today_ist())
"
# Should match IST timezone (UTC+5:30)
```

---

## 📞 Support

**Questions about:**
- **Feature:** See BIRTHDAY_REMINDER_GUIDE.md
- **WhatsApp Template:** See WHATSAPP_BIRTHDAY_TEMPLATE_SETUP.md
- **Code Changes:** See BIRTHDAY_FEATURE_IMPLEMENTATION_SUMMARY.md
- **Quick Lookup:** See BIRTHDAY_QUICK_REFERENCE.md

---

## 🎯 Next Steps After Deployment

1. **Monitor:** Check logs daily for "Birthday template sent" messages
2. **User Feedback:** Collect feedback on message content/timing
3. **Analytics:** Track birthday reminder open rates (if available from WhatsApp)
4. **Future:** Consider enhancements like birthday photos, discounts, etc.

---

## 📝 Rollback Plan (If Needed)

```bash
# 1. Revert code
git revert <commit-hash>

# 2. Remove env variable from all .env files
# (Delete line: WHATSAPP_TEMPLATE_BIRTHDAY=birthday_celebration)

# 3. Restart backend
docker-compose down
docker-compose up -d

# 4. Archive template in Meta Business Manager (optional)
# No database cleanup needed - birthday records are safe
```

---

## ✨ Success Indicators

✅ You'll know it's working when:

1. **Seed test data** creates a pet with "Birthday Celebration" record
2. **Logs show** "Birthday template sent to ..." messages
3. **Test user** (+919095705762) receives birthday message
4. **Dashboard** shows birthday reminders in reminder history
5. **No errors** in logs, all graceful error handling

---

## 🎉 Feature Live!

Once deployed, birthday reminders will:
- ✅ Send automatically 7 days before each pet's birthday
- ✅ Work for all pets with DOB on file
- ✅ Work for both dogs and cats
- ✅ Use celebratory WhatsApp template
- ✅ Integrate seamlessly with existing reminder system
- ✅ Support all existing reminder features (snooze, reschedule, etc.)

**Target Deployment Time:** 15 minutes
**Testing Time:** 5-10 minutes
**Go-Live Time:** Now ready! 🚀

---

**Last Updated:** March 12, 2026
**Status:** ✅ Ready for Production
