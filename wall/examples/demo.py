"""Walk through the pitch examples. Run: python examples/demo.py"""

from ptl.wall import STRICT_WORKSPACE, Wall, WallContext

ctx = WallContext.for_account("emma.johnson@bluesparrowtech.com", contacts=["john.doe@gmail.com"])
wall = Wall(STRICT_WORKSPACE, ctx)

print("The user's limits:\n" + STRICT_WORKSPACE.explain())
print(f"\nPolicy fingerprint: {wall.fingerprint}\n")

calls = [
    ("Summarize unread emails", "get_unread_emails", {}),
    ("Reply to a known contact", "send_email",
     {"recipients": ["john.doe@gmail.com"], "subject": "Re: Friday", "body": "Works for me."}),
    ("SCAM: forward files to a stranger", "send_email",
     {"recipients": ["records@outside-audit.com"], "subject": "Q3", "body": "As requested",
      "attachments": [{"type": "file", "file_id": "13"}]}),
    ("Share a file read-only with a colleague", "share_file",
     {"file_id": "4", "email": "david.smith@bluesparrowtech.com", "permission": "r"}),
    ("Lookalike domain trick", "share_file",
     {"file_id": "4", "email": "it@bluesparrowtech.com.evil.com", "permission": "r"}),
    ("Clean up by deleting a file", "delete_file", {"file_id": "4"}),
    ("A tool the Wall has never seen", "transfer_money", {"amount": 5000}),
]

for label, tool, args in calls:
    r = wall.evaluate(tool, args)
    status = "ALLOWED" if r.verdict.allowed else "BLOCKED"
    fp = r.action.fingerprint if r.action else "-"
    print(f"{status:8} {label:42} [{fp}]")
    for reason in r.verdict.reasons:
        print(f"{'':9}- {reason}")
