# 🧭 Found IT

**Found IT** is a campus-based **Lost & Found Web Application** built using **Python (Flask)**.  
It allows students to post items they’ve *found* or *lost* within the campus, making it easier to connect and return belongings to their rightful owners.


## 🚀 Features

### 👤 Authentication
- Secure **student login and registration** using institute email only.
- Passwords stored using **hashed encryption**

### 🎒 Lost & Found System
- Post items you’ve **found** or **lost** with:
  - Item name
  - Description
  - Category (e.g., mobile, laptop, ID card)
  - Place (where the item was found/lost)
  - Hostel blocks
  - Up to 3 images
- Each post is displayed publicly for easy browsing.

### 🔍 Search & Filter
- Filter items by **category** or **place**
- Search items using **keywords** from item name or description

### 🕐 Post Management
- The original poster can **mark an item as claimed/found**
- Once confirmed, the post auto-deletes after a **60-second timer**

### 🧠 Smart Interface
- Clean, user-friendly design with dark UI theme  
- Flash messages auto-disappear after 10 seconds  
- Separate tabs for **Lost** and **Found** items


## ⚙️ Tech Stack

| Component | Technology |
|------------|-------------|
| **Frontend** | HTML, CSS, JavaScript (Bootstrap) |
| **Backend** | Python (Flask) |
| **Database** | SQLite |
