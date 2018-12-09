### Arango Agency Analyzer

Allows analysis of arangodbs agency logs.

# Usage

Given a JSON encoded agency log in a file, start with
```
python aaa.py <file>
```
Close the program via `:q`.

On the left side you can see a list of all log entries ordered by time. Use the `UP/DOWN` to navigate.
The right side contains different views of information. Currently supported modes are
    - `log`: display the selected log entry
    - `store`: display the state of the agency at the selected moment (reconstructed from log entries)
In both modes one can scroll the text using `UP/DOWN` keys. Focus can be switched using `LEFT/RIGHT`.
To change the view mode either use `F1/F2` or `:view <mode>`.

When in `store` mode with focus on the view side, use `p` to modify the displayed path
of the agency. Use `TAB` to auto complete your input.

