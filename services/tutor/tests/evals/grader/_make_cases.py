"""One-off generator for the hand-written eval cases (kept so they can be regenerated/extended)."""
import json
from pathlib import Path

CASES = [
    {
        "file": "01_beginner_steps_1_2.json",
        "name": "Beginner: names steps 1 and 2 only, with basic definitions",
        "focus_node_id": None,
        "prior_context": "",
        "transcript": (
            "Ok so Ind AS 115 is about revenue. There is a five step model. The first step is to identify the "
            "contract with the customer, a contract is basically an agreement between the parties that creates "
            "enforceable rights and obligations, it can be written or oral or even implied. The second step is "
            "identifying the performance obligations, which are the promises to transfer distinct goods or services "
            "to the customer. After that there are more steps about price and recognising revenue but I don't "
            "remember the details."
        ),
        "expect": {
            "ind_as_115.step_1": "VERIFIED",
            "ind_as_115.step_2": "VERIFIED",
            "ind_as_115.step_3": "!VERIFIED",
            "ind_as_115.step_4": "!VERIFIED",
            "ind_as_115.step_5": "!VERIFIED",
            "ind_as_115.step_1.criteria": "NOT_MENTIONED",
            "ind_as_115.step_2.distinct": "NOT_MENTIONED",
        },
    },
    {
        "file": "02_advanced_full_model.json",
        "name": "Advanced finalist: all five steps with level-2 detail on three of them",
        "focus_node_id": None,
        "prior_context": "",
        "transcript": (
            "Ind AS 115 applies a five step model. Step one, identify the contract, which is an agreement creating "
            "enforceable rights and obligations, written, oral or implied. Step two, identify the performance "
            "obligations, meaning each promise to transfer a distinct good or service or a series of distinct goods "
            "that are substantially the same. Step three, determine the transaction price, which is the consideration "
            "the entity expects to be entitled to, excluding amounts collected for third parties like GST. Within that, "
            "variable consideration such as rebates, bonuses and penalties is estimated using either the expected value "
            "method, which is a probability weighted amount suited to a large number of similar contracts, or the most "
            "likely amount, which suits binary outcomes like a completion bonus. Step four, allocate the transaction "
            "price to the performance obligations so that each gets an amount depicting the consideration expected for "
            "it, on a relative standalone selling price basis. Step five, recognise revenue when or as each obligation "
            "is satisfied, which is when control transfers to the customer, either over time or at a point in time. "
            "Over time applies if any one of three criteria is met: the customer simultaneously receives and consumes "
            "the benefit, or the entity creates or enhances an asset the customer controls as it is created, or the "
            "asset has no alternative use to the entity and the entity has an enforceable right to payment for "
            "performance to date."
        ),
        "expect": {
            "ind_as_115.step_1": "VERIFIED",
            "ind_as_115.step_2": "VERIFIED",
            "ind_as_115.step_3": "VERIFIED",
            "ind_as_115.step_4": "VERIFIED",
            "ind_as_115.step_5": "VERIFIED",
            "ind_as_115.step_3.variable_consideration": "VERIFIED",
            "ind_as_115.step_5.over_time_criteria": "VERIFIED",
            "ind_as_115.step_3.constraint": "NOT_MENTIONED",
            "ind_as_115.step_4.ssp_estimation": "NOT_MENTIONED",
        },
    },
    {
        "file": "03_teach_back_wrong_ssp.json",
        "name": "Teach-back on SSP: confident but wrong (allocates on cost)",
        "focus_node_id": "ind_as_115.step_4.ssp",
        "prior_context": "Tutor asked: Now explain the relative standalone selling price basis back to me in your own words, with an example.",
        "transcript": (
            "Sure. So when you have a bundle you allocate the price to each item based on what it cost the company to "
            "make. So if the phone cost six hundred and the case cost fifty you split the price in that ratio. That is "
            "the standalone selling price method."
        ),
        "expect": {"ind_as_115.step_4.ssp": "GAP"},
    },
    {
        "file": "04_teach_back_partial_over_time.json",
        "name": "Teach-back on over-time criteria: two of three criteria, third incomplete",
        "focus_node_id": "ind_as_115.step_5.over_time_criteria",
        "prior_context": "Tutor asked: Explain the three criteria for recognising revenue over time back to me, with an example of each.",
        "transcript": (
            "Revenue is over time if the customer receives and consumes the benefit at the same time as we perform, "
            "like a cleaning service. Or if we are building something on the customer's own land so they control it "
            "as we build it. And the third one is about the asset having no alternative use to us. You only need one "
            "of the three."
        ),
        "expect": {"ind_as_115.step_5.over_time_criteria": "PARTIAL"},
    },
    {
        "file": "05_teach_back_verified_financing.json",
        "name": "Teach-back on significant financing component: complete and correct",
        "focus_node_id": "ind_as_115.step_3.financing",
        "prior_context": "Tutor asked: Explain the significant financing component back to me in your own words, with an example.",
        "transcript": (
            "If the timing of payment gives either party a significant financing benefit, we adjust the transaction "
            "price for the time value of money so that revenue reflects the cash selling price at the date of transfer. "
            "The difference is unwound as interest income or interest expense, it's presented separately from revenue. "
            "There is a practical expedient: if the gap between transfer and payment is one year or less you don't "
            "adjust. For example if I deliver machinery today and the customer pays in three years with no interest, "
            "revenue is the discounted amount and the unwinding is interest income."
        ),
        "expect": {"ind_as_115.step_3.financing": "VERIFIED"},
    },
    {
        "file": "06_vague_mention_not_verified.json",
        "name": "Vague name-dropping evidences nothing: NOT_MENTIONED, not PARTIAL",
        "focus_node_id": None,
        "prior_context": "",
        "transcript": (
            "I know there are five steps and there is something about variable consideration and a constraint, and "
            "standalone selling price comes in somewhere, and licences have special rules, and there's contract assets "
            "and contract liabilities on the balance sheet."
        ),
        "expect": {
            "ind_as_115.step_3.variable_consideration": "NOT_MENTIONED",
            "ind_as_115.step_3.constraint": "NOT_MENTIONED",
            "ind_as_115.step_4.ssp": "NOT_MENTIONED",
            "ind_as_115.step_5.licences": "NOT_MENTIONED",
            "ind_as_115.cross_cutting.presentation": "NOT_MENTIONED",
        },
    },
    {
        "file": "07_misconception_warranties.json",
        "name": "Stated misconception: all warranties are separate performance obligations",
        "focus_node_id": None,
        "prior_context": "",
        "transcript": (
            "Step two is performance obligations. One thing I remember is that any warranty given with a product is "
            "always a separate performance obligation, so you always defer part of the revenue for every warranty "
            "until the warranty period ends."
        ),
        "expect": {"ind_as_115.step_2.warranties": "GAP"},
    },
    {
        "file": "08_stt_noise_correct_content.json",
        "name": "Speech-recognition noise around a correct SSP explanation must still verify",
        "focus_node_id": "ind_as_115.step_4.ssp",
        "prior_context": "Tutor asked: Explain the relative standalone selling price basis back to me, with an example.",
        "transcript": (
            "um so the stand alone selling price the S S P is basically the price we would sell that good or service "
            "for on its own separately to a customer uh the best evidence is an observable price when we actually sell "
            "it separately in similar circumstances and then we allocate the total transaction price in proportion to "
            "the S S Ps so like if software sells alone for sixty thousand and support alone for forty thousand and the "
            "bundle is ninety thousand we give fifty four thousand to software and thirty six to support"
        ),
        "expect": {"ind_as_115.step_4.ssp": "VERIFIED"},
    },
]

out = Path(__file__).resolve().parent / "cases"
out.mkdir(exist_ok=True)
for c in CASES:
    fname = c.pop("file")
    (out / fname).write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", fname)
