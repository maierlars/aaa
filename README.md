# Arango Agency Analyzer

Allows analysis of arangodbs agency logs.

## Usage

Given a JSON encoded agency log in a file, start with
```
python aaa.py <log file> <snapshot file>
python aaa.py http|https://<endpoint> <jwt>
```
Close the program via `:q`.

On the left side you can see a list of all log entries ordered by time. Use the `UP/DOWN` to navigate.
The right side contains different views of information. Currently supported modes are

- `log`: display the selected log entry
- `store`: display the state of the agency at the selected moment (reconstructed from log entries)

In both modes one can scroll the text using `UP/DOWN` keys. Focus can be switched using `TAB`.
To change the view mode either use `F1/F2` or `:view <mode>`.

When in `store` mode with focus on the view side, use `p` to modify the displayed path
of the agency. Use `TAB` to auto complete your input.

When in the left hand side, use `f` to enter a regular expression to filter entries by requested paths.
Use `g` to do a basic grep like search on the log entries. Reset filters via `R`.

To dump the content of the JSON view into a file use `:dump filename`.

### Save and Restore states

You can save and restore states of the analyizer. To store a state use:
`:(s|save|store) [name]`
where name is the name of the state. if empty a prompt will open.

To restore a state use:
`:(r|restore) [name]`
again name is optional and if empty a prompt with autocomplete will open.

You can use `0-9` keys as shortcuts to restore state `"0"-"9"`. To save the state
use `ALT + "x"`.
