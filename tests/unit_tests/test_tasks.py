import pytest
from itertools import repeat
from unittest.mock import MagicMock

from prefect import flow
from prefect.tasks import task, task_input_hash
from prefect.futures import PrefectFuture
from prefect.client import OrionClient


class TestTaskCall:
    def test_task_called_outside_flow_raises(self):
        @task
        def foo():
            pass

        with pytest.raises(
            RuntimeError, match="Tasks cannot be called outside of a flow"
        ):
            foo()

    def test_task_called_inside_flow(self):
        @task
        def foo(x):
            return x

        @flow
        def bar():
            return foo(1)
            # Returns a future so we can run assertions outside of the flow context

        flow_future = bar()
        task_future = flow_future.result().data
        assert isinstance(task_future, PrefectFuture)
        assert task_future.result().data == 1

    @pytest.mark.parametrize("error", [ValueError("Hello"), None])
    def test_state_reflects_result_of_run(self, error):
        @task
        def bar():
            if error:
                raise error

        @flow(version="test")
        def foo():
            return bar()

        flow_future = foo()
        task_future = flow_future.result().data
        state = task_future.result()

        # Assert the final state is correct
        assert state.is_failed() if error else state.is_completed()
        assert state.data is error

    def test_task_runs_correctly_populate_dynamic_keys(self):
        @task
        def bar():
            return "foo"

        @flow(version="test")
        def foo():
            return bar(), bar()

        flow_future = foo()
        task_futures = [item for item in flow_future.result().data]

        orion_client = OrionClient()
        task_runs = [
            orion_client.read_task_run(task_run.run_id) for task_run in task_futures
        ]

        # Assert dynamic key is set correctly
        assert task_runs[0].dynamic_key == "0"
        assert task_runs[1].dynamic_key == "1"

    def test_task_called_with_task_dependency(self):
        @task
        def foo(x):
            return x

        @task
        def bar(y):
            return y + 1

        @flow
        def test_flow():
            return bar(foo(1))

        flow_future = test_flow()
        task_future = flow_future.result().data
        assert task_future.result().data == 2


class TestTaskRetries:
    @pytest.mark.parametrize("always_fail", [True, False])
    def test_task_respects_retry_count(self, always_fail):
        mock = MagicMock()
        exc = ValueError()

        @task(retries=3)
        def flaky_function():
            mock()

            # 3 retries means 4 attempts
            # Succeed on the final retry unless we're ending in a failure
            if not always_fail and mock.call_count == 4:
                return True

            raise exc

        @flow
        def test_flow():
            return flaky_function()

        flow_future = test_flow()
        task_future = flow_future.result().data

        if always_fail:
            state = task_future.result()
            assert state.is_failed()
            assert state.data is exc
            assert mock.call_count == 4
        else:
            state = task_future.result()
            assert state.is_completed()
            assert state.data is True
            assert mock.call_count == 4

        client = OrionClient()
        states = client.read_task_run_states(task_future.run_id)
        state_names = [state.name for state in states]
        assert state_names == [
            "Pending",
            "Running",
            "Awaiting Retry",
            "Running",
            "Awaiting Retry",
            "Running",
            "Awaiting Retry",
            "Running",
            "Failed" if always_fail else "Completed",
        ]

    def test_task_only_uses_necessary_retries(self):
        mock = MagicMock()
        exc = ValueError()

        @task(retries=3)
        def flaky_function():
            mock()
            if mock.call_count == 2:
                return True
            raise exc

        @flow
        def test_flow():
            return flaky_function()

        flow_future = test_flow()
        task_future = flow_future.result().data

        state = task_future.result()
        assert state.is_completed()
        assert state.data is True
        assert mock.call_count == 2

        client = OrionClient()
        states = client.read_task_run_states(task_future.run_id)
        state_names = [state.name for state in states]
        assert state_names == [
            "Pending",
            "Running",
            "Awaiting Retry",
            "Running",
            "Completed",
        ]

    def test_task_respects_retry_delay(self, monkeypatch):
        mock = MagicMock()
        sleep = MagicMock()  # Mock sleep for fast testing
        monkeypatch.setattr("time.sleep", sleep)

        @task(retries=1, retry_delay_seconds=43)
        def flaky_function():
            mock()

            if mock.call_count == 2:
                return True

            raise ValueError("try again, but only once")

        @flow
        def test_flow():
            return flaky_function()

        flow_future = test_flow()
        task_future = flow_future.result().data

        assert sleep.call_count == 1
        # due to rounding, the expected sleep time will be less than 43 seconds
        # we test for a 3-second window to account for delays in CI
        assert 40 < sleep.call_args[0][0] < 43

        client = OrionClient()
        states = client.read_task_run_states(task_future.run_id)
        state_names = [state.name for state in states]
        assert state_names == [
            "Pending",
            "Running",
            "Awaiting Retry",
            "Running",
            "Completed",
        ]


class TestTaskCaching:
    def test_repeated_task_call_within_flow_is_not_cached_by_default(self):
        @task
        def foo(x):
            return x

        @flow
        def bar():
            return foo(1).result(), foo(1).result()

        flow_future = bar()
        first_state, second_state = flow_future.result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Completed"
        assert second_state.data == first_state.data

    def test_cache_hits_within_flows_are_cached(self):
        @task(cache_key_fn=lambda *_: "cache hit")
        def foo(x):
            return x

        @flow
        def bar():
            return foo(1).result(), foo(2).result()

        flow_future = bar()
        first_state, second_state = flow_future.result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Cached"
        assert second_state.data == first_state.data

    def test_many_repeated_cache_hits_within_flows_cached(self):
        @task(cache_key_fn=lambda *_: "cache hit")
        def foo(x):
            return x

        @flow
        def bar():
            foo(1)
            calls = repeat(foo(1), 5)
            return [call.result() for call in calls]

        flow_future = bar()
        states = flow_future.result().data
        assert all(state.name == "Cached" for state in states)

    def test_cache_hits_between_flows_are_cached(self):
        @task(cache_key_fn=lambda *_: "cache hit")
        def foo(x):
            return x

        @flow
        def bar(x):
            return foo(x).result()

        first_state = bar(1).result().data
        second_state = bar(2).result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Cached"
        assert second_state.data == first_state.data

    def test_cache_misses_arent_cached(self):

        # this hash fn won't return the same value twice
        def mutating_key(*_, tally=[]):
            tally.append("x")
            return "call tally:" + "".join(tally)

        @task(cache_key_fn=mutating_key)
        def foo(x):
            return x

        @flow
        def bar():
            return foo(1).result(), foo(1).result()

        flow_future = bar()
        first_state, second_state = flow_future.result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Completed"

    def test_cache_key_fn_context(self):
        def stringed_context(context, args):
            return str(context.flow_run_id)

        @task(cache_key_fn=stringed_context)
        def foo(x):
            return x

        @flow
        def bar():
            return foo("something").result(), foo("different").result()

        first_future = bar()
        first_state, second_state = first_future.result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Cached"
        assert second_state.data == first_state.data

        second_future = bar()
        third_state, fourth_state = second_future.result().data
        assert third_state.name == "Completed"
        assert fourth_state.name == "Cached"
        assert fourth_state.data == first_state.data

    def test_cache_key_fn_arg_inputs_are_stable(self):
        def stringed_inputs(context, args):
            return str(args)

        @task(cache_key_fn=stringed_inputs)
        def foo(a, b, c=3):
            return a + b + c

        @flow
        def bar():
            return (
                foo(1, 2, 3).result(),
                foo(1, b=2).result(),
                foo(c=3, a=1, b=2).result(),
            )

        flow_future = bar()
        first_state, second_state, third_state = flow_future.result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Cached"
        assert third_state.name == "Cached"

        assert second_state.data == first_state.data
        assert third_state.data == first_state.data


class TestCacheFunctionBuiltins:
    def test_task_input_hash_within_flows(self):
        @task(cache_key_fn=task_input_hash)
        def foo(x):
            return x

        @flow
        def bar():
            return foo(1).result(), foo(2).result(), foo(1).result()

        flow_future = bar()
        first_state, second_state, third_state = flow_future.result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Completed"
        assert third_state.name == "Cached"
        assert first_state.data != second_state.data
        assert first_state.data == third_state.data

    def test_task_input_hash_between_flows(self):
        @task(cache_key_fn=task_input_hash)
        def foo(x):
            return x

        @flow
        def bar(x):
            return foo(x).result()

        first_state = bar(1).result().data
        second_state = bar(2).result().data
        third_state = bar(1).result().data
        assert first_state.name == "Completed"
        assert second_state.name == "Completed"
        assert third_state.name == "Cached"
        assert first_state.data != second_state.data
        assert first_state.data == third_state.data
