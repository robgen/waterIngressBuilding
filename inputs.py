"""inputs.py — command-line model inputs shared by cli.py and batch.py.

Defines the building/pathway/run-control flags once and converts parsed
arguments into the model inputs: engine.SimConfig and (paths, membranes).
"""

import warnings

import engine
import fragility
from pump import SumpPump


def add_model_args(p):
    """Add the flags that describe the building, its pathways and the run."""
    # ── ingress pathways ──────────────────────────────────────────────────────
    p.add_argument('--ingress', '-i', default=None,
                   help='Ground-floor ingress pathways CSV (unified format). '
                        'Omit for basement-only cases with no ground-floor pathway.')
    p.add_argument('--basement-ingress', default=None,
                   help='Exterior→basement pathways CSV (unified format); every row '
                        'flows into the basement.')
    p.add_argument('--membrane', default=None,
                   help='Membrane CSV (unified format; rows with group_id > 0 '
                        'and fragility state columns).')

    # ── building geometry ─────────────────────────────────────────────────────
    p.add_argument('--floor', '-f', type=float, required=True,
                   help='Ground-floor plan area (m²).')
    p.add_argument('--floor-datum', type=float, default=0.0,
                   help='Internal floor elevation above external ground datum (m). '
                        'Use 0.10 for a building with a 10 cm doorstep.')

    # ── basement ──────────────────────────────────────────────────────────────
    p.add_argument('--basement-area', type=float, default=0.0,
                   help='Basement plan area (m²). If >0, a basement zone is created.')
    p.add_argument('--basement-floor-elevation', type=float, default=None,
                   help='Basement floor elevation relative to datum (m, negative = below).')
    p.add_argument('--basement-ceiling-elevation', type=float, default=None,
                   help='Basement ceiling elevation on the datum (m). '
                        'Default: --floor-datum (ceiling flush with internal floor).')
    p.add_argument('--basement-bypass-height', type=float, default=None,
                   help='Sill of the ground↔basement bypass connection (m).')
    p.add_argument('--basement-bypass-area', type=float, default=0.0,
                   help='Area of the ground↔basement bypass (m²).')
    p.add_argument('--basement-bypass-coeff', type=float, default=0.6,
                   help='Discharge coefficient Cd of the ground↔basement bypass (–). Default: 0.6.')

    # ── sump + pump (always used together, --sumppump-* prefix) ──────────────
    # The sump is a pit whose top is at the basement floor.
    p.add_argument('--sumppump-area', type=float, default=0.0,
                   help='Sump pit plan area (m²). >0 activates the sump+pump module.')
    p.add_argument('--sumppump-base-elevation', type=float, default=None,
                   help='Sump pit base elevation (m); must be below '
                        '--basement-floor-elevation (pit depth = floor − base).')
    p.add_argument('--sumppump-opening-area', type=float, default=None,
                   help='Area of the pit opening at the basement floor through which '
                        'basement water drains into the sump (m²). Default: --sumppump-area.')
    p.add_argument('--sumppump-opening-coeff', type=float, default=0.6,
                   help='Discharge coefficient of the pit opening (–). Default: 0.6.')
    p.add_argument('--sumppump-on-level', type=float, default=None)
    p.add_argument('--sumppump-off-level', type=float, default=None)
    p.add_argument('--sumppump-shutoff-head', type=float, default=None)
    p.add_argument('--sumppump-curve-coeff', type=float, default=None)
    p.add_argument('--sumppump-pipe-loss-coeff', type=float, default=0.0)
    p.add_argument('--sumppump-availability', type=float, default=1.0)

    # ── exterior velocity ─────────────────────────────────────────────────────
    p.add_argument('--velocity-mode', default='zero',
                   choices=['zero', 'power_law', 'file'],
                   help="Velocity mode: 'zero' (default), 'power_law' (v=a·h^b), "
                        "or 'file' (3rd hydrograph column).")
    p.add_argument('--velocity-power-law-a', type=float, default=1.5,
                   help='Power-law coefficient a in v=a·h^b. Default: 1.5.')
    p.add_argument('--velocity-power-law-b', type=float, default=0.5,
                   help='Power-law exponent b in v=a·h^b. Default: 0.5.')

    # ── time stepping ─────────────────────────────────────────────────────────
    p.add_argument('--time-units', '-u', default='minutes',
                   choices=list(engine.TIME_UNIT_SECONDS),
                   help='Time units of the hydrograph files and --dt.')
    p.add_argument('--dt', type=float, default=1.0,
                   help='Simulation timestep (in --time-units). Default: 1 unit.')

    # ── Monte Carlo ───────────────────────────────────────────────────────────
    p.add_argument('--n-replicates', type=int, default=1,
                   help='Number of Monte Carlo replicates. >1 runs the fragility ensemble.')
    p.add_argument('--random-seed', type=int, default=None)
    p.add_argument('--output-percentiles', nargs='+', type=int,
                   default=[10, 25, 50, 75, 90])


def _sumppump_from_args(args):
    if not args.sumppump_area or args.sumppump_area <= 0.0:
        return None
    required = ['sumppump_base_elevation',
                'sumppump_on_level', 'sumppump_off_level',
                'sumppump_shutoff_head', 'sumppump_curve_coeff']
    missing = [k for k in required if getattr(args, k) is None]
    if missing:
        print(f'WARNING: --sumppump-area set but missing: '
              f'{[k.replace("_", "-") for k in missing]}. Sump disabled.')
        return None
    return SumpPump(
        sump_area=args.sumppump_area,
        sump_base_elevation=args.sumppump_base_elevation,
        opening_area=args.sumppump_opening_area,
        opening_coeff=args.sumppump_opening_coeff,
        pump_on_level=args.sumppump_on_level,
        pump_off_level=args.sumppump_off_level,
        pump_shutoff_head=args.sumppump_shutoff_head,
        pump_curve_coeff=args.sumppump_curve_coeff,
        pipe_loss_coeff=args.sumppump_pipe_loss_coeff,
        pump_availability=args.sumppump_availability,
    )


def config_from_args(args, **extra) -> engine.SimConfig:
    """Build SimConfig from the flags added by add_model_args.

    `extra` sets the SimConfig fields owned by the calling script
    (e.g. animate, compute_forces).
    """
    return engine.SimConfig(
        floor_area=args.floor,
        dt=args.dt * engine.TIME_UNIT_SECONDS[args.time_units],
        floor_datum=args.floor_datum,
        basement_area=args.basement_area,
        basement_floor_elevation=args.basement_floor_elevation or 0.0,
        basement_ceiling_elevation=args.basement_ceiling_elevation,
        basement_connection_height=args.basement_bypass_height,
        basement_connection_area=args.basement_bypass_area,
        basement_connection_coeff=args.basement_bypass_coeff,
        sumppump=_sumppump_from_args(args),
        n_replicates=args.n_replicates,
        random_seed=args.random_seed,
        output_percentiles=tuple(args.output_percentiles),
        velocity_mode=args.velocity_mode,
        velocity_power_law_a=args.velocity_power_law_a,
        velocity_power_law_b=args.velocity_power_law_b,
        time_units=args.time_units,
        **extra,
    )


def pathways_from_args(args):
    """Return (paths, membranes) from --ingress, --basement-ingress, --membrane."""
    return fragility.load_pathways(args.ingress, args.basement_ingress, args.membrane)


def plain_warnings():
    """Print model warnings as 'WARNING: message' lines on the command line."""
    warnings.formatwarning = lambda message, category, *args, **kwargs: f'WARNING: {message}\n'
