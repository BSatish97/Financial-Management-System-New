"""
Database Setup Script for Financial Management System
Run this script to create the database and tables
"""

import MySQLdb
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
}

def create_database():
    """Create the financial_management database and tables"""
    try:
        # Connect to MySQL without specifying a database
        conn = MySQLdb.connect(
            host=DB_CONFIG['host'],
            user=DB_CONFIG['user'],
            passwd=DB_CONFIG['password']
        )
        cursor = conn.cursor()
        
        print("📝 Creating database...")
        
        # Create database
        cursor.execute("CREATE DATABASE IF NOT EXISTS financial_management")
        print("✓ Database 'financial_management' ready")
        
        # Select database
        cursor.execute("USE financial_management")
        
        # Create tables
        print("📝 Creating tables...")
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                financial_goal VARCHAR(255),
                budgets DECIMAL(10,2) DEFAULT 0.00,
                budget DECIMAL(10,2) DEFAULT 0.00,
                otp VARCHAR(6) DEFAULT NULL,
                otp_expiry DATETIME DEFAULT NULL,
                is_verified TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✓ Users table created")
        
        # Transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                amount DECIMAL(10,2) NOT NULL,
                category VARCHAR(100) NOT NULL,
                date DATE NOT NULL,
                description TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                KEY user_date_idx (user_id, date)
            )
        """)
        print("✓ Transactions table created")
        
        # Budgets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                category VARCHAR(100) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("✓ Budgets table created")
        
        # Documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                filename VARCHAR(255) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                file_path VARCHAR(255) NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_size BIGINT DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("✓ Documents table created")
        
        # Document transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                document_id INT NOT NULL,
                user_id INT NOT NULL,
                category VARCHAR(100),
                amount DECIMAL(10,2),
                date DATE,
                description TEXT,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("✓ Document transactions table created")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n✅ Database setup completed successfully!")
        return True
        
    except MySQLdb.Error as e:
        print(f"\n❌ MySQL Error: {e}")
        if e.args[0] == 2003:
            print("   → MySQL server is not running. Please start XAMPP/MySQL.")
        elif e.args[0] == 1045:
            print("   → Authentication failed. Check username/password.")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Financial Management System - Database Setup")
    print("=" * 50)
    
    if create_database():
        sys.exit(0)
    else:
        print("\n⚠️  Setup failed. Please check the errors above.")
        sys.exit(1)
