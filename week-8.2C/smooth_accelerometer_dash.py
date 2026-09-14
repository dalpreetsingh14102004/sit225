import threading
from collections import deque
from datetime import datetime

from arduino_iot_cloud import ArduinoCloudClient
from dash import Dash, dcc, html, Input, Output, no_update
import plotly.graph_objects as go


# ============================================================
# REUSABLE LIVE ACCELEROMETER DASHBOARD
# ============================================================

class LiveAccelerometerDashboard:
    """
    Reusable Arduino IoT Cloud + Plotly Dash accelerometer monitor.

    The class:
    1. Connects to Arduino IoT Cloud
    2. Receives X, Y and Z accelerometer values
    3. Stores data in rolling deque buffers
    4. Uses Plotly Dash extendData for smooth updates
    5. Keeps only the latest max_points samples
    """

    def __init__(
        self,
        device_id,
        secret_key,
        max_points=100,
        refresh_ms=200
    ):

        # ----------------------------------------------------
        # USER SETTINGS
        # ----------------------------------------------------

        self.device_id = device_id
        self.secret_key = secret_key

        self.max_points = max_points
        self.refresh_ms = refresh_ms


        # ----------------------------------------------------
        # ROLLING HISTORY BUFFERS
        # ----------------------------------------------------

        self.time_buffer = deque(maxlen=max_points)

        self.x_buffer = deque(maxlen=max_points)
        self.y_buffer = deque(maxlen=max_points)
        self.z_buffer = deque(maxlen=max_points)


        # ----------------------------------------------------
        # NEW DATA WAITING FOR PLOTLY
        # ----------------------------------------------------

        self.pending_times = deque()

        self.pending_x = deque()
        self.pending_y = deque()
        self.pending_z = deque()


        # ----------------------------------------------------
        # LATEST ARDUINO CLOUD VALUES
        # ----------------------------------------------------

        self.latest_x = None
        self.latest_y = None
        self.latest_z = None


        # Thread lock protects the buffers
        self.buffer_lock = threading.Lock()


        # ----------------------------------------------------
        # CREATE DASH APP
        # ----------------------------------------------------

        self.app = Dash(__name__)

        self._create_layout()
        self._create_callback()


    # ========================================================
    # STORE SENSOR SAMPLE
    # ========================================================

    def _store_sample(self):

        # Wait until all three axes have received a value
        if (
            self.latest_x is None
            or self.latest_y is None
            or self.latest_z is None
        ):
            return


        # Use a real datetime value for a cleaner time axis
        timestamp = datetime.now()

        x_value = float(self.latest_x)
        y_value = float(self.latest_y)
        z_value = float(self.latest_z)


        with self.buffer_lock:

            # -----------------------------------------------
            # Rolling history buffer
            # -----------------------------------------------

            self.time_buffer.append(timestamp)

            self.x_buffer.append(x_value)
            self.y_buffer.append(y_value)
            self.z_buffer.append(z_value)


            # -----------------------------------------------
            # Data waiting to be appended to Plotly
            # -----------------------------------------------

            self.pending_times.append(timestamp)

            self.pending_x.append(x_value)
            self.pending_y.append(y_value)
            self.pending_z.append(z_value)


        # Display incoming values in PowerShell
        print(
            f"{timestamp.strftime('%H:%M:%S.%f')[:-3]} | "
            f"X={x_value:.3f} | "
            f"Y={y_value:.3f} | "
            f"Z={z_value:.3f}"
        )


    # ========================================================
    # ARDUINO CLOUD CALLBACKS
    # ========================================================

    def _on_x_change(self, client, value):

        self.latest_x = value

        self._store_sample()


    def _on_y_change(self, client, value):

        self.latest_y = value

        self._store_sample()


    def _on_z_change(self, client, value):

        self.latest_z = value

        self._store_sample()


    # ========================================================
    # CONNECT TO ARDUINO IOT CLOUD
    # ========================================================

    def _run_arduino_cloud(self):

        print("")
        print("========================================")
        print("Connecting to Arduino IoT Cloud")
        print("========================================")
        print("")


        client = ArduinoCloudClient(
            device_id=self.device_id,
            username=self.device_id,
            password=self.secret_key
        )


        # Register the synced Cloud variables
        client.register(
            "Accelerometer_X",
            value=None,
            on_write=self._on_x_change
        )


        client.register(
            "Accelerometer_Y",
            value=None,
            on_write=self._on_y_change
        )


        client.register(
            "Accelerometer_Z",
            value=None,
            on_write=self._on_z_change
        )


        print("Arduino Cloud client started.")
        print("Waiting for smartphone accelerometer data...")
        print("Move or tilt your iPhone.")
        print("")


        # Arduino client continuously listens for updates
        client.start()


    # ========================================================
    # INITIAL PLOTLY GRAPH
    # ========================================================

    def _create_figure(self):

        fig = go.Figure()


        # X axis
        fig.add_trace(

            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name="X"
            )

        )


        # Y axis
        fig.add_trace(

            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name="Y"
            )

        )


        # Z axis
        fig.add_trace(

            go.Scatter(
                x=[],
                y=[],
                mode="lines",
                name="Z"
            )

        )


        fig.update_layout(

            title="Live Smartphone Accelerometer",

            xaxis_title="Time",

            yaxis_title="Acceleration",

            legend_title="Axis",

            # Keep user zoom/pan state while updating
            uirevision="accelerometer",

            margin=dict(
                l=60,
                r=40,
                t=70,
                b=60
            )

        )


        # Cleaner timestamps
        fig.update_xaxes(
            tickformat="%H:%M:%S",
            nticks=10
        )


        return fig


    # ========================================================
    # DASH LAYOUT
    # ========================================================

    def _create_layout(self):

        self.app.layout = html.Div(

            [

                html.H1(
                    "Live Smartphone Accelerometer"
                ),


                html.P(
                    "Arduino IoT Cloud → Python → "
                    "Rolling deque buffer → Plotly Dash → extendData"
                ),


                html.P(
                    "Move or tilt the smartphone to see "
                    "live X, Y and Z accelerometer values."
                ),


                dcc.Graph(

                    id="accelerometer-graph",

                    figure=self._create_figure()

                ),


                # Dash checks the pending buffer frequently
                dcc.Interval(

                    id="graph-update",

                    interval=self.refresh_ms,

                    n_intervals=0

                )

            ],

            style={
                "width": "95%",
                "margin": "auto"
            }

        )


    # ========================================================
    # EXTENDDATA CALLBACK
    # ========================================================

    def _create_callback(self):

        @self.app.callback(

            Output(
                "accelerometer-graph",
                "extendData"
            ),

            Input(
                "graph-update",
                "n_intervals"
            )

        )

        def update_graph(n):

            with self.buffer_lock:

                # No new sensor data
                if len(self.pending_times) == 0:
                    return no_update


                # Copy pending values
                times = list(self.pending_times)

                xs = list(self.pending_x)
                ys = list(self.pending_y)
                zs = list(self.pending_z)


                # Remove them from pending buffer
                self.pending_times.clear()

                self.pending_x.clear()
                self.pending_y.clear()
                self.pending_z.clear()


            # ------------------------------------------------
            # extendData adds only NEW points
            # ------------------------------------------------

            new_data = {

                "x": [
                    times,
                    times,
                    times
                ],

                "y": [
                    xs,
                    ys,
                    zs
                ]

            }


            # Trace 0 = X
            # Trace 1 = Y
            # Trace 2 = Z

            trace_indices = [0, 1, 2]


            # Keep only the newest max_points
            return (
                new_data,
                trace_indices,
                self.max_points
            )


    # ========================================================
    # START SYSTEM
    # ========================================================

    def run(
        self,
        host="127.0.0.1",
        port=8050
    ):

        # Arduino Cloud runs independently of Dash
        cloud_thread = threading.Thread(

            target=self._run_arduino_cloud,

            daemon=True

        )


        cloud_thread.start()


        print("")
        print("========================================")
        print("Starting Plotly Dash")
        print("========================================")
        print("")
        print(f"Open:")
        print(f"http://{host}:{port}")
        print("")


        self.app.run(

            host=host,

            port=port,

            debug=False

        )


# ============================================================
# SIMPLE REUSABLE WRAPPER FUNCTION
# ============================================================

def create_live_accelerometer_dashboard(
    device_id,
    secret_key,
    max_points=100,
    refresh_ms=200
):
    """
    Simple API for creating the accelerometer dashboard.

    Parameters
    ----------
    device_id : str
        Arduino IoT Cloud Python device ID.

    secret_key : str
        Arduino IoT Cloud Python device secret key.

    max_points : int
        Maximum number of graph points retained.

    refresh_ms : int
        Dash graph update interval in milliseconds.

    Returns
    -------
    LiveAccelerometerDashboard
        Configured dashboard object.
    """

    return LiveAccelerometerDashboard(

        device_id=device_id,

        secret_key=secret_key,

        max_points=max_points,

        refresh_ms=refresh_ms

    )


# ============================================================
# RUN THE PROGRAM
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Import credentials from separate local file
    # --------------------------------------------------------

    from arduino_credentials import DEVICE_ID, SECRET_KEY


    # --------------------------------------------------------
    # USE THE WRAPPER/API
    # --------------------------------------------------------

    dashboard = create_live_accelerometer_dashboard(

        device_id=DEVICE_ID,

        secret_key=SECRET_KEY,

        max_points=100,

        refresh_ms=200

    )


    # Start Arduino Cloud + Dash
    dashboard.run()