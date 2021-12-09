"""Starting with a forms.csv, add metadata for all columns we know about.
"""

from pathlib import Path

from lexedata import cli
from lexedata.util.add_metadata import add_metadata

if __name__ == "__main__":
    parser = cli.parser(__doc__)
    parser.add_argument(
        "--keep-forms",
        action="store_true",
        default="false",
        help="Do not overwrite forms.csv to add new columns, even if that means forms.csv and the metadata do not correspond to each other.",
    )
    args = parser.parse_args()
    logger = cli.setup_logging(args)

    fname = Path("forms.csv")

    ds = add_metadata(fname)

    if args.metadata.exists():
        logger.critical("Metadata file %s already exists!", args.metadata)
        cli.Exit.CLI_ARGUMENT_ERROR()

    ds.write_metadata(args.metadata)

    # TODO: If we can get the need to re-write the FormTable out of the
    # metadata guesser, we can default to not re-writing it and warn if it
    # would be necessary.
    if not args.keep_forms:
        ds.write(FormTable=list(ds["FormTable"]))
        logger.info("FormTable re-written.")

    ds.validate(log=logger)
