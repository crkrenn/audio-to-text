# voice-to-text
Simple python script for converting mp3 to text.

This script has been tested with python3.12 on os x. The pytests pass, and command line tests with both the free and paid apis work.

Using the paid api requires a google cloud service account and `gcp-service-account-key.json` file or link in the script directory.

Please contact the author with any questions. Pull requests are welcomed!

-Chris Krenn

Example generic `gcp-service-account-key.json` file:
{
  "type": "service_account",
  "project_id": "XXX",
  "private_key_id": "XXX",
  "private_key": "XXX",
  "client_email": "XXX",
  "client_id": "XXX",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/XXX.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
