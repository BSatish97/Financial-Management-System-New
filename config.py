import os


DB_CONFIG = {
	"host": os.environ.get("DB_HOST", "127.0.0.1"),
	"user": os.environ.get("DB_USER", "root"),
	"password": os.environ.get("DB_PASSWORD", ""),
	"database": os.environ.get("DB_NAME", "financial_management"),
	"port": int(os.environ.get("DB_PORT", "3306")),
}
