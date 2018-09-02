import os
import re
import pprint
from .AnalyserResult import AnalyserResult
from .BaseAnalyser import AnalyserError, BaseAnalyser

pp = pprint.PrettyPrinter(indent=4)


class Oyente(BaseAnalyser):
    """
    Interface to execute Oyente analyser.
    """

    def __init__(self, debug, timeout):
        """ Constructor.
        If you set environment variable OYENTE, that will be used as path to executable to invoke.
        If that is not set, we run using "oyente".
        :param debug: Whether debug mode is on
        :param timeout: Test case execution timeout
        """
        super().__init__(os.environ.get('OYENTE', 'oyente'), debug, timeout)

        self._read_version()

    @staticmethod
    def get_name():
        """
        :return: Analyser name
        """
        return 'Oyente'

    @property
    def version(self):
        """
        :return: Oyente version
        """
        return self._version

    def run_test(self, sol_file, run_opts):
        """
        Execute Oyente on specified solidity file.
        NOTE:   Oyente does not return address (byte offset) information, thus it has been
                decided to use "location" instead of address for Oyente.
        Issue format:
            'filename': File path and name
            'lineno': Line number
            'linepos': Line position
            'location': Location of found issue. Contains file path and line
            'title': Issue title
            'type': Issue type. Warning at the moment
            'code': Source code part that raises issues
        :param sol_file: Path to solidity file
        :return: AnalyserResult
        :raises AnalyserError:
        :raises AnalyserTimeoutError:
        """
        # It is possible to output result into json file when '-j' parameter is passed. However,
        # json file contains errors in same text format which has to be parsed anyway.
        # Thus, lets just parse output, at least there will be no need to cleanup anything
        run_opts += ['-a', '-ce', '-s', str(sol_file)]
        res = self._execute(*run_opts)

        # No issues found
        if res['returncode'] == 0:
            return AnalyserResult(res['elapsed'])
        # Oyente returns 1 when issues found, other errors indicates that something went wrong
        if res['returncode'] != 1:
            raise AnalyserError('Failed to get run Oyente', res['returncode'], res['cmd'])

        # Oyente outputs report info into stderr
        output = res['stderr'].decode('utf-8').strip()

        if self.debug:
            pp.pprint(output)
            print('=' * 30)

        # Seems like Oyente failed. Usually file not found or compilation error
        if 'CRITICAL' in output:
            raise AnalyserError('Failed to get run Oyente: {}'.format(output), res['returncode'], res['cmd'])

        try:
            issues = self._parse_report(output)
        except Exception as e:
            raise AnalyserError(str(e), res['returncode'], res['cmd'])

        return AnalyserResult(res['elapsed'], issues)

    def _parse_report(self, output):
        """
        Parses output
        :param output: Oyente output
        :return: List of issues
        """
        issues = []
        # Failures are printed
        # Each statement starts with "INFO:symExec:"
        statements = output.split("INFO:symExec:")

        # Extract failure reports from list of statements
        for stat in statements:
            # Failure statements consists of path, location, title and code.
            # If statements does not match regex it will be skipped
            # Single statement may contain multiple failures
            matches = re.findall(r'(.+):(\d+):(\d+): (.+)\.[\r\n]+(.+)', stat, re.MULTILINE)

            for m in matches:
                # If it is "Warning" failure (and currently there are only warnings)
                # remove it from message and set type to warning
                _type = "Warning" if m[3].startswith("Warning") else None
                title = m[3].replace("Warning: ", "", 1)

                issues.append({
                    'filename': m[0],
                    'lineno': int(m[1]),
                    'linepos': int(m[2]),
                    'location': '{}:{}'.format(m[0], m[1]),
                    'title': title,
                    'type': _type,
                    'code': m[4].strip()
                })

        return issues

    def _read_version(self):
        """
        Executes Oyente and reads versions from output
        :return: Oyente version string
        :raises AnalyserError:
        """
        res = self._execute('--version')

        if res['returncode'] != 0:
            raise AnalyserError('Execution failed', res['returncode'], res['cmd'])

        output = res['stdout'].decode('utf-8')
        m = re.search(r'oyente version (.+)', output)
        if not m:
            raise AnalyserError('Can not read Oyente version: "{}"'.format(output), cmd=res['cmd'])

        self._version = m.group(1)
