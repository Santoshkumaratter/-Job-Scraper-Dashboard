"""
Management command to setup Google Sheets configuration
"""
from django.core.management.base import BaseCommand
from google_sheets.models import GoogleSheetConfig


class Command(BaseCommand):
    help = 'Setup Google Sheets configuration for job export'
    
    def handle(self, *args, **options):
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("📊 Google Sheets Configuration Setup"))
        self.stdout.write("="*60 + "\n")
        
        # Check if config already exists
        existing = GoogleSheetConfig.objects.filter(is_active=True).first()
        if existing:
            self.stdout.write(self.style.WARNING(f"✓ Active configuration already exists: {existing.name}"))
            self.stdout.write(f"  Spreadsheet ID: {existing.spreadsheet_id}")
            self.stdout.write(f"  Worksheet: {existing.worksheet_name}\n")
            
            response = input("Do you want to create a new configuration? (y/n): ")
            if response.lower() != 'y':
                self.stdout.write("Cancelled.")
                return
        
        # Get user input
        self.stdout.write("\nPlease provide the following information:\n")
        
        name = input("Configuration Name (e.g., 'Main Jobs Sheet'): ").strip()
        if not name:
            name = "Default Jobs Export"
        
        spreadsheet_id = input("Google Spreadsheet ID (from URL): ").strip()
        if not spreadsheet_id:
            self.stdout.write(self.style.ERROR("\n❌ Spreadsheet ID is required!"))
            self.stdout.write("\nHow to find Spreadsheet ID:")
            self.stdout.write("1. Open your Google Sheet")
            self.stdout.write("2. Look at the URL: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit")
            self.stdout.write("3. Copy the SPREADSHEET_ID part\n")
            return
        
        worksheet_name = input("Worksheet/Tab Name (default: 'Jobs'): ").strip()
        if not worksheet_name:
            worksheet_name = "Jobs"
        
        # Create configuration
        config = GoogleSheetConfig.objects.create(
            name=name,
            spreadsheet_id=spreadsheet_id,
            worksheet_name=worksheet_name,
            is_active=True,
            auto_export=True,
            include_headers=True
        )
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS("✅ Google Sheets Configuration Created!"))
        self.stdout.write("="*60)
        self.stdout.write(f"\nName: {config.name}")
        self.stdout.write(f"Spreadsheet ID: {config.spreadsheet_id}")
        self.stdout.write(f"Worksheet: {config.worksheet_name}")
        self.stdout.write(f"Active: {config.is_active}")
        self.stdout.write(f"Auto Export: {config.auto_export}")
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.WARNING("📝 Next Steps:"))
        self.stdout.write("="*60)
        self.stdout.write("1. Make sure Google Sheets API is enabled")
        self.stdout.write("2. Add service account credentials to .env file")
        self.stdout.write("3. Share your Google Sheet with the service account email")
        self.stdout.write("4. Test export by clicking 'Export to Google Sheets' button")
        self.stdout.write("\n✓ Configuration is ready to use!\n")

