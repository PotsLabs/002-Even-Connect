"""
Data source integrations — external systems that feed content to glasses via protocol.

Each integration module shows how to:
  1. Connect to external data source (Obsidian, Slack, Calendar, etc.)
  2. Fetch/format content
  3. Use protocol.connect functions to send to glasses

Pattern:
  ExternalService → Formatter → protocol.connect.send_text/send_bmp_to_glass → Glasses

Available integrations:
  - obsidian.py    : Obsidian vault notes and attachments
"""
