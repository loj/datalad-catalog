import json
import logging
import os
import sys
from os.path import (
    abspath,
    curdir,
)
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from datalad.distribution.dataset import datasetmethod
from datalad.interface.base import (
    Interface,
    build_doc,
)
from datalad.interface.results import get_status_dict
from datalad.interface.utils import eval_results
from datalad.log import log_progress
from datalad.support.constraints import EnsureChoice
from datalad.support.exceptions import InsufficientArgumentsError
from datalad.support.param import Parameter
from jsonschema import (
    Draft202012Validator,
    RefResolver,
    ValidationError,
)

from datalad_catalog.meta_item import MetaItem
from datalad_catalog.utils import read_json_file
from datalad_catalog.webcatalog import (
    Node,
    WebCatalog,
)

# Create named logger
lgr = logging.getLogger("datalad.catalog.catalog")

# Decoration auto-generates standard help
@build_doc
# All extension commands must be derived from Interface
class Catalog(Interface):
    # first docstring line is used a short description in the cmdline help
    # the rest is put in the verbose help and manpage
    """Generate web-browser-based user interface for browsing metadata of a
    DataLad dataset.

    (Long description of arbitrary volume.)
    """

    # parameters of the command, must be exhaustive
    _params_ = dict(
        # name of the parameter, must match argument name
        catalog_action=Parameter(
            args=("catalog_action",),
            # documentation
            doc="""This is the subcommand to be executed by datalad-catalog.
            Options include: create, add, remove, serve, set-super, and validate.
            Example: ''""",
            # type checkers, constraint definition is automatically
            # added to the docstring
            constraints=EnsureChoice(
                "create", "add", "remove", "serve", "set-super", "validate"
            ),
        ),
        catalog_dir=Parameter(
            # cmdline argument definitions, incl aliases
            args=("-c", "--catalog_dir"),
            # documentation
            doc="""Directory where the catalog is located or will be created.
            Example: ''""",
        ),
        metadata=Parameter(
            # cmdline argument definitions, incl aliases
            args=("-m", "--metadata"),
            # documentation
            doc="""Path to input metadata. Multiple input types are possible:
            - A '.json' file containing an array of JSON objects related to a
             single datalad dataset.
            - A stream of JSON objects/lines
            Example: ''""",
        ),
        dataset_id=Parameter(
            # cmdline argument definitions, incl aliases
            args=("-i", "--dataset_id"),
            # documentation
            doc="""
            Example: ''""",
        ),
        dataset_version=Parameter(
            # cmdline argument definitions, incl aliases
            args=("-v", "--dataset_version"),
            # documentation
            doc="""
            Example: ''""",
        ),
        force=Parameter(
            # cmdline argument definitions, incl aliases
            args=("-f", "--force"),
            # documentation
            doc="""If content for the user interface already exists in the catalog
            directory, force this content to be overwritten. Content
            overwritten with this flag include the 'artwork' and 'assets'
            directories and the 'index.html' and 'config.json' files. Content in
            the 'metadata' directory remain untouched.
            Example: ''""",
            action="store_true",
            default=False,
        ),
        config_file=Parameter(
            # cmdline argument definitions, incl aliases
            args=("-y", "--config-file"),
            # documentation
            doc="""Path to config file in YAML or JSON format. Default config is read
            from datalad_catalog/templates/config.json
            Example: ''""",
        ),
    )

    @staticmethod
    # decorator binds the command to the Dataset class as a method
    @datasetmethod(name="catalog")
    # generic handling of command results (logging, rendering, filtering, ...)
    @eval_results
    # signature must match parameter list above
    # additional generic arguments are added by decorators
    def __call__(
        catalog_action: str,
        catalog_dir=None,
        metadata=None,
        dataset_id=None,
        dataset_version=None,
        force: bool = False,
        config_file=None,
    ):
        """
        [summary]

        Args:
            catalog_action (str): [description]
            catalog_dir ([type], optional): [description]. Defaults to None.
            metadata ([type], optional): [description]. Defaults to None.
            dataset_id ([type], optional): [description]. Defaults to None.
            dataset_version ([type], optional): [description]. Defaults to None.
            force (bool, optional): [description]. Defaults to False.

        Raises:
            InsufficientArgumentsError: [description]
            InsufficientArgumentsError: [description]
            InsufficientArgumentsError: [description]

        Yields:
            [type]: [description]
        """

        # TODO: check if schema is valid (move to tests)
        # Draft202012Validator.check_schema(schema)

        # If action is validate, only metadata required
        if catalog_action == "validate":
            yield from _validate_metadata(
                None,
                metadata,
                None,
                None,
                None,
                None,
            )
            return

        # Error out if `catalog_dir` argument was not supplied
        if catalog_dir is None:
            err_msg = f"No catalog directory supplied: Datalad catalog can only operate on a path to a directory. Argument: -c, --catalog_dir."
            raise InsufficientArgumentsError(err_msg)

        # Instantiate WebCatalog class
        ctlg = WebCatalog(catalog_dir, dataset_id, dataset_version, config_file)
        # catalog_path = Path(catalog_dir)
        # catalog_exists = catalog_path.exists() and catalog_path.is_dir()

        # Hanlde case where a non-catalog directory already exists at path argument
        # Should prevent overwriting
        if ctlg.path_exists() and not ctlg.is_created():
            err_msg = f"A non-catalog directory already exists at {catalog_dir}. Please supply a different path."
            raise FileExistsError(err_msg)

        # Catalog should exist for all actions except create (for create action: unless force flag supplied)
        if not ctlg.is_created():
            if catalog_action != "create":
                err_msg = f"Catalog does not exist: datalad catalog {catalog_action} can only operate on an existing catalog, please supply a path to an existing directory with the catalog argument: -c, --catalog_dir."
                raise InsufficientArgumentsError(err_msg)
        else:
            if catalog_action == "create":
                if not force:
                    err_msg = f"Catalog already exists: overwriting catalog assets (not catalog metadata) is only possible when using the force argument: -f, --force."
                    raise InsufficientArgumentsError(err_msg)

        # Call relevant function based on action
        # Action-specific argument parsing as well as results yielding are done within action-functions
        CALL_ACTION = {
            "create": _create_catalog,
            "serve": _serve_catalog,
            "add": _add_to_catalog,
            "remove": _remove_from_catalog,
            "set-super": _set_super_of_catalog,
        }
        yield from CALL_ACTION[catalog_action](
            ctlg, metadata, dataset_id, dataset_version, force, config_file
        )


# Internal functions to execute based on catalog_action parameter
def _create_catalog(
    catalog: WebCatalog,
    metadata,
    dataset_id: str,
    dataset_version: str,
    force: bool,
    config_file: str,
):
    """"""
    # If catalog does not exist, create it
    # If catalog exists and force flag is True, overwrite assets of existing catalog
    msg = ""
    if not catalog.is_created():
        catalog.create()
        msg = f"Catalog successfully created at: {catalog.location}"
    else:
        if force:
            catalog.create(force)
            msg = f"Catalog assets successfully overwritten at: {catalog.location}"
    # Yield created/overwitten status message
    yield get_status_dict(
        action="catalog create", path=abspath(curdir), status="ok", message=msg
    )
    # If metadata was also supplied, add this to the catalog
    if metadata is not None:
        yield from _add_to_catalog(
            catalog, metadata, dataset_id, dataset_version, force, config_file
        )


def _add_to_catalog(
    catalog: WebCatalog,
    metadata,
    dataset_id: str,
    dataset_version: str,
    force: bool,
    config_file: str,
):
    """
    [summary]
    """
    if metadata is None:
        err_msg = f"No metadata supplied: Datalad catalog has to be supplied with metadata in the form of a path to a file containing a JSON array, or JSON lines stream, using the argument: -m, --metadata."
        raise InsufficientArgumentsError(err_msg)

    # Then we need to do the following:
    # 1. establish input type (file, file-with-json-array, file-with-json-lines, command line stdout / stream)

    #    - for now: assume file-with-json-array (data exported by `datalad meta-dump` and all exported objects added to an array in file)
    # 2. instantiate translator
    # 3. read input based on type
    #    - for now: load data from input file
    # 4. For each metadata object in input, call translator

    # 2. Instantiate single translator
    # translate = Translator()

    # TODO: Establish input type
    # 3. Read input
    # metadata = read_json_file(metadata)
    # This metadata should be the dataset and file level metadata of a single dataset
    # TODO: insert checks to verify this
    # TODO: decide whether to allow metadata dictionaries from multiple datasets

    with open(metadata) as file:
        i = 0
        for line in file:
            i += 1
            # meta_dict = line.rstrip()
            meta_dict = json.loads(line.rstrip())

            # Check if item/line is a dict
            if not isinstance(meta_dict, dict):
                err_msg = f"Metadata item not of type dict: metadata items should be passed to datalad catalog as JSON objects adhering to the catalog schema."
                lgr.warning(err_msg)
                # raise TypeError(err_msg)
            # Validate dict against catalog schema
            try:
                catalog.VALIDATOR.validate(meta_dict)
            except ValidationError as e:
                err_msg = f"Schema validation failed in LINE {i}: \n\n{e}"
                raise ValidationError(err_msg) from e
            # If validation passed, translate into catalog files
            MetaItem(catalog, meta_dict)
            # Translator(catalog, meta_dict)

    # TODO: should we write all files here?
    # Set parent catalog of orphans
    orphans = [
        Node._instances[inst]
        for inst in Node._instances
        if not hasattr(Node._instances[inst], "parent_catalog")
        or not Node._instances[inst].parent_catalog
    ]
    for orphan in orphans:
        orphan.parent_catalog = catalog

    # [inst for inst in Node._instances if not hasattr(Node._instances[inst], 'parent_catalog')]
    for blob in Node._instances:
        inst = Node._instances[blob]
        parent_path = inst.get_location().parents[0]
        fn = inst.get_location()
        created = inst.is_created()

        if hasattr(inst, "node_path") and inst.type != "dataset":
            setattr(inst, "path", str(inst.node_path))
        if hasattr(inst, "node_path") and inst.type == "directory":
            setattr(inst, "name", inst.node_path.name)

        meta_dict = vars(inst)
        keys_to_pop = [
            "node_path",
            "long_name",
            "md5_hash",
            "file_name",
            "parent_catalog",
        ]
        for key in keys_to_pop:
            meta_dict.pop(key, None)

        if not created:
            parent_path.mkdir(parents=True, exist_ok=True)
            with open(fn, "w") as f:
                json.dump(vars(inst), f)
        else:
            with open(fn, "r+") as f:
                f.seek(0)
                json.dump(vars(inst), f)
                f.truncate()

    msg = "Metadata items successfully added to catalog"
    yield get_status_dict(
        action="catalog add", path=abspath(curdir), status="ok", message=msg
    )


def _remove_from_catalog(
    catalog: WebCatalog,
    metadata,
    dataset_id: str,
    dataset_version: str,
    force: bool,
    config_file: str,
):
    """
    [summary]
    """
    # remove argument checks
    if not dataset_id or not dataset_version:
        err_msg = f"Dataset ID and/or VERSION missing: datalad catalog remove requires both the ID (-i, --dataset_id) and VERSION (-v, --dataset_version) of the dataset to be removed from the catalog"
        yield get_status_dict(
            action=f"catalog remove",
            path=abspath(curdir),  # reported paths MUST be absolute
            status="error",
            message=err_msg,
        )
        sys.exit(err_msg)


def _serve_catalog(
    catalog: WebCatalog,
    metadata,
    dataset_id: str,
    dataset_version: str,
    force: bool,
    config_file: str,
):
    """
    Start a local http server for viewing/testing a local catalog

    Args:
        catalog (WebCatalog): the catalog to be served
        metadata (dict): unused
        dataset_id (str): unused
        dataset_version (str): unused
        force (bool): unused

    Yields:
        (dict): result record
    """
    os.chdir(catalog.location)
    import http.server
    import socketserver

    PORT = 8000
    HOSTNAME = "localhost"
    # HOSTNAME = '127.0.0.1'
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer((HOSTNAME, PORT), Handler) as httpd:
        print(f"\nServing catalog at: http://{HOSTNAME}:{PORT}/")
        print(
            "- navigate to this address in your browser to test the catalog locally"
        )
        print("- press CTRL+C to stop local testing\n")
        httpd.serve_forever()

    msg = "Dataset served"
    yield get_status_dict(
        action="catalog serve", path=abspath(curdir), status="ok", message=msg
    )


def _set_super_of_catalog(
    catalog: WebCatalog,
    metadata,
    dataset_id: str,
    dataset_version: str,
    force: bool,
    config_file: str,
):
    """
    [summary]
    """
    err_msg = (
        "Dataset ID and/or VERSION missing: datalad catalog set-super requires both the ID"
        " (-i, --dataset_id) and VERSION (-v, --dataset_version) of the dataset that is to be"
        " used as the catalog's super dataset"
    )
    if not dataset_id or not dataset_version:
        raise InsufficientArgumentsError(err_msg)

    catalog.set_main_dataset()

    msg = "Superdataset successfully set for catalog"
    yield get_status_dict(
        action="catalog set-super",
        path=abspath(curdir),
        status="ok",
        message=msg,
    )


def _validate_metadata(
    catalog: WebCatalog,
    metadata,
    dataset_id: str,
    dataset_version: str,
    force: bool,
    config_file: str,
):
    """"""
    # First check metadata was supplied via -m flag
    if metadata is None:
        err_msg = f"No metadata supplied: datalad catalog has to be supplied with metadata in the form of a path to a file containing a JSON array, or JSON lines stream, using the argument: -m, --metadata."
        raise InsufficientArgumentsError(err_msg)

    # Setup schema parameters
    package_path = Path(__file__).resolve().parent
    templates_path = package_path / "templates"
    schemas = ["catalog", "dataset", "file", "authors", "extractors"]
    schema_store = {}
    for s in schemas:
        schema_path = templates_path / str("jsonschema_" + s + ".json")
        schema = read_json_file(schema_path)
        schema_store[schema["$id"]] = schema

    # Access the schema against which incoming metadata items will be validated
    catalog_schema = schema_store["https://datalad.org/catalog.schema.json"]
    RESOLVER = RefResolver.from_schema(catalog_schema, store=schema_store)
    num_lines = _get_line_count(metadata)

    # Open metadata file and validate line by line
    with open(metadata) as file:
        i = 0
        for line in file:
            i += 1
            log_progress(
                lgr.info,
                "catalogvalidate",
                f"Start validation of metadata in {metadata}",
                total=num_lines,
                update=i,
                label="metadata validation against catalog schema",
                unit=" Lines",
            )
            meta_dict = json.loads(line.rstrip())
            # Check if item/line is a dict
            if not isinstance(meta_dict, dict):
                err_msg = f"Metadata item not of type dict: metadata items should be passed to datalad catalog as JSON objects adhering to the catalog schema."
                lgr.warning(err_msg)
            # Validate dict against schema
            try:
                Draft202012Validator(
                    catalog_schema, resolver=RESOLVER
                ).validate(meta_dict)
            except ValidationError as e:
                err_msg = (
                    f"Schema validation failed in LINE {i}/{num_lines}: \n\n{e}"
                )
                raise ValidationError(err_msg) from e

    msg = "Metadata successfully validated"
    yield get_status_dict(
        action="catalog validate",
        path=abspath(curdir),
        status="ok",
        message=msg,
    )


def _get_line_count(file):
    with open(file) as f:
        for i, _ in enumerate(f):
            pass
    return i + 1
