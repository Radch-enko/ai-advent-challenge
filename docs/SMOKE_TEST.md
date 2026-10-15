# Live OpenAI smoke test

This check is optional and sends the selected repository's supported documentation and test question to the configured OpenAI endpoint. Run it only in a fictitious or otherwise approved test repository.

## Prepare

1. Install Code Assistance with pipx or an editable install.
2. Configure chat_model, embedding_model, and base_url in the Code Assistance project's root `config.toml`.
3. Set OPENAI_API_KEY in the current shell or in the Code Assistance project's local `.env` file.
4. Create a temporary Git repository with an invented README and one invented Markdown file under docs/.
5. Configure `git_mcp.command` to the bundled `code-assistance-git-mcp` executable.

Do not put a real API key in the repository, config file, prompt, or test output.

## Run

From the temporary repository:

~~~sh
code-assistance
~~~

Confirm that the endpoint and data-sharing warning appear before indexing begins. Then ask:

~~~text
/help Where is the made-up project layout described?
/help What is the current branch?
/help What changed in the working tree?
/exit
~~~

Check that the documentation answer cites the invented source path and line range, the branch answer reflects the temporary repository's current branch, and the Git answer cites actual paths returned by MCP. Change the branch and ask again in the same session; the new branch should appear without reindexing.

The smoke test is not part of automated checks and must not be run against a personal repository without explicit approval.
