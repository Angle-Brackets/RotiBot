from pyston import PystonClient, File as PystonFile
from pyston.models import Output
from io import TextIOWrapper
from typing import Set, List, Optional

class RotiExecutionEngine():
    def __init__(self):
        self._client : PystonClient = PystonClient()
        self._run_timeout = 10_000 # 10 seconds max to run.
        self._compile_timeout = 10_000 # 10 seconds max to compile.
        self.execution_endpoint = r"https://emkc.org/api/v2/piston/execute"
        self.runtimes_endpoint = r"https://emkc.org/api/v2/piston/runtimes"
        self._languages : Set[str] = set()
    
    async def execute(self, language : str, file : TextIOWrapper, args : List[str] | None) -> Output:
        output = await self._client.execute(
            language=language,
            files=[PystonFile(file)],
            args=args,
            run_timeout=self._run_timeout,
            compile_timeout=self._compile_timeout
        )

        return output

    def validate_output(self, output : Output) -> Optional[str]:
        # This basically never fires, you should look at the output.success block.
        if output.compile_stage and not output.compile_stage.code and output.compile_stage.signal:
            return f"An error has occured compiling with signal {output.compile_stage.signal}:\n{output.compile_stage.output}"
        if not output.success:
            return f"An error has occured running with signal {output.run_stage.signal} (You may have exceeded the size of stdout or your script timed out!):\n{output.run_stage.output}"
    
    async def get_languages(self) -> Set[str]:
        if not self._languages:
            self._languages = await self._client.languages()
        return self._languages