"""Live routing check for T-75 (customer-requested changes), every message style.
Never completes a change: a yes/no is answered "no", an OTP step is abandoned.
Run from the host with EVAL_API_KEY, EVAL_USERNAME, EVAL_PASSWORD set:
  python3 experiments/eval_t75.py
"""
import sys

from eval_conversation import CL, chat, login

OTP, CONF, BS = "OTP_REQUIRED", "CONFIRMATION_REQUIRED", "BANKING_SERVICE"
SEL = "ACCOUNT_SELECTION_REQUIRED"
REPORT = {(BS, "card_requests", "report_lost_card"), (SEL, "card_requests", "report_lost_card")}
FREEZE = {(OTP, "card_services", "frezz_unfrezz"), CL}
COMPLAINT = {(CONF, "support", "submit_complaint"), CL}
NICK = {(CONF, "profile_update", "update_nickname"), CL}
ADDR = {(CONF, "profile_update", "update_address"), CL}
EMAIL = {(OTP, "profile_update", "update_email"), CL}
MOBILE = {(OTP, "profile_update", "update_mobile"), CL}
PHOTO = {(BS, "profile_update", "update_profile_image")}

CASES = [
    ("lost", "i lost my card", REPORT),
    ("lost", "lost card", REPORT),
    ("lost", "card churi hoye gese", REPORT),
    ("lost", "My wallet was stolen this morning with my debit card inside it.", REPORT),
    ("freeze", "block my card", FREEZE),
    ("freeze", "I lost my card, please block it right now", FREEZE),
    ("complaint", "complain", COMPLAINT),
    ("complaint", "i want to file a complaint", COMPLAINT),
    ("complaint", "Your app keeps crashing every time I open my statement. This is unacceptable and I want to lodge a formal complaint.", COMPLAINT),
    ("complaint", "branch er staff kharap behave korse, abhijog dite chai", COMPLAINT),
    ("nickname", "change my nickname to Rafi", NICK),
    ("nickname", "nickname change", NICK),
    ("nickname", "amar nickname Rafi kore dao", NICK),
    ("address", "update my address", ADDR),
    ("address", "change my present address to House 12, Road 5, Dhanmondi, Dhaka", ADDR),
    ("address", "We moved last month. My permanent address is now Village Kamarpara, Gazipur.", ADDR),
    ("email", "change my email to rafi.test@example.com", EMAIL),
    ("email", "update email", EMAIL),
    ("email", "amar email bodlate chai", EMAIL),
    ("mobile", "change my mobile number to 01812345678", MOBILE),
    ("mobile", "i got a new phone number", MOBILE),
    ("mobile", "amar number change korbo 01712345678", MOBILE),
    ("photo", "change my profile picture", PHOTO),
    ("photo", "upload a new photo", PHOTO),
    ("blocked", "reset my card pin", {CL}),
]


def main():
    token = login()
    ok = 0
    for kind, msg, accepted in CASES:
        reply, r = chat(token, msg)
        got = (r["type"], r.get("category"), r.get("service")) if r else ("NO_RESULT", None, None)
        hit = got in accepted
        ok += hit
        print(f"{'OK ' if hit else 'BAD'} [{kind}] {msg[:70]!r} -> {got}", flush=True)
        print(f"      reply: {reply[:260]!r}", flush=True)
        if r and r["type"] in (CONF, OTP, SEL, "CLARIFICATION_REQUIRED"):
            chat(token, "no")  # never complete a change; clear any pending step
    print(f"\n{ok}/{len(CASES)} correct")
    sys.exit(0 if ok == len(CASES) else 1)


if __name__ == "__main__":
    main()
