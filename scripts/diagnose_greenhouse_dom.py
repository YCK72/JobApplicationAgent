from __future__ import annotations

import sys

from app.browser.manager import BrowserSession


def safe_attr(control, name: str):
    try:
        return control.get_attribute(name)
    except Exception:
        return None


def safe_evaluate(control, expression: str):
    try:
        return control.evaluate(expression)
    except Exception:
        return None


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m scripts.diagnose_greenhouse_dom "
            "<greenhouse-job-url>"
        )
        return 1

    job_url = sys.argv[1].strip()

    print("=" * 80)
    print("GREENHOUSE READ-ONLY DOM DIAGNOSTIC")
    print("=" * 80)
    print()
    print(f"URL: {job_url}")
    print()

    session = BrowserSession()

    try:
        session.start()
        session.navigate(job_url)

        page = session.page
        controls = page.locator("input, textarea, select")

        count = controls.count()

        print(f"Controls found: {count}")
        print()

        for index in range(count):
            control = controls.nth(index)

            print("=" * 80)
            print(f"CONTROL #{index + 1}")
            print("=" * 80)

            tag_name = safe_evaluate(
                control,
                "(el) => el.tagName.toLowerCase()",
            )

            print(f"tag:              {tag_name}")
            print(f"id:               {safe_attr(control, 'id')}")
            print(f"name:             {safe_attr(control, 'name')}")
            print(f"type:             {safe_attr(control, 'type')}")
            print(f"role:             {safe_attr(control, 'role')}")
            print(f"required:         {safe_attr(control, 'required')}")
            print(f"aria-required:    {safe_attr(control, 'aria-required')}")
            print(f"aria-label:       {safe_attr(control, 'aria-label')}")
            print(f"aria-labelledby:  {safe_attr(control, 'aria-labelledby')}")
            print(f"aria-controls:    {safe_attr(control, 'aria-controls')}")
            print(f"aria-expanded:    {safe_attr(control, 'aria-expanded')}")
            print(f"autocomplete:     {safe_attr(control, 'autocomplete')}")
            print(f"placeholder:      {safe_attr(control, 'placeholder')}")
            print(f"class:            {safe_attr(control, 'class')}")

            if safe_attr(control, "role") == "combobox":
                print("combobox diagnostics:")

                labelled_by = safe_attr(
                    control,
                    "aria-labelledby",
                )

                controls_id = safe_attr(
                    control,
                    "aria-controls",
                )

                print(f"  labelled by:    {labelled_by}")
                print(f"  controls id:    {controls_id}")

                if labelled_by:
                    label_text = safe_evaluate(
                        control,
                        """
                        (el) => {
                            const id = el.getAttribute(
                                "aria-labelledby"
                            );

                            if (!id) {
                                return null;
                            }

                            const label =
                                document.getElementById(id);

                            return label
                                ? (label.innerText || "").trim()
                                : null;
                        }
                        """,
                    )

                    print(
                        f"  label text:     {label_text!r}"
                    )

                option_data = safe_evaluate(
                    control,
                    """
                    (el) => {
                        const result = [];

                        const selectors = [
                            '[role="option"]',
                            'option'
                        ];

                        let node = el;

                        for (
                            let depth = 0;
                            depth < 6 && node;
                            depth++
                        ) {
                            for (const selector of selectors) {
                                const matches =
                                    node.querySelectorAll(selector);

                                for (const match of matches) {
                                    const text = (
                                        match.innerText ||
                                        match.textContent ||
                                        ""
                                    ).trim();

                                    if (text) {
                                        result.push({
                                            text,
                                            role:
                                                match.getAttribute(
                                                    "role"
                                                ),
                                            id:
                                                match.getAttribute(
                                                    "id"
                                                ),
                                        });
                                    }
                                }
                            }

                            node = node.parentElement;
                        }

                        return result;
                    }
                    """,
                )

                print(
                    f"  nearby options: {option_data!r}"
                )

            parent_tag = safe_evaluate(
                control,
                "(el) => el.parentElement?.tagName?.toLowerCase() || null",
            )

            parent_class = safe_evaluate(
                control,
                "(el) => el.parentElement?.className || null",
            )

            print(f"parent tag:       {parent_tag}")
            print(f"parent class:     {parent_class}")

            nearby_text = safe_evaluate(
                control,
                """
                (el) => {
                    let node = el;

                    for (let depth = 0; depth < 4 && node; depth++) {
                        const text = (node.innerText || "").trim();

                        if (text) {
                            return text.slice(0, 500);
                        }

                        node = node.parentElement;
                    }

                    return null;
                }
                """,
            )

            print("nearby text:")
            print(repr(nearby_text))
            print()

        print("=" * 80)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 80)
        print()
        print("No fields were filled.")
        print("No controls were clicked.")
        print("No files were uploaded.")
        print("No form was submitted.")

        return 0

    except Exception as exc:
        print()
        print("=" * 80)
        print("DIAGNOSTIC FAILED")
        print("=" * 80)
        print(f"{type(exc).__name__}: {exc}")
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())