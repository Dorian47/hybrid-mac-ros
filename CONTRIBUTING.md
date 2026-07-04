# Contributing

Thank you for your interest in contributing to the Hybrid TDMA/CSMA project!

## How to Contribute

1. **Fork** the repository
2. Create a **feature branch** (`git checkout -b feature/my-feature`)
3. Make your changes
4. **Test** on real SDR hardware or the ROS simulation environment
5. Submit a **Pull Request**

## Coding Guidelines

- **Python**: Follow PEP 8. Use type hints where practical.
- **C (driver)**: Follow Linux kernel coding style (`scripts/checkpatch.pl`).
- **Shell**: Prefer POSIX-compatible syntax. Use `shellcheck` to lint.
- **ROS**: Follow [ROS C++/Python style guide](http://wiki.ros.org/StyleGuide).

## Pull Request Checklist

- [ ] Code compiles / runs without errors
- [ ] No hardcoded personal paths, IPs, or credentials
- [ ] New features are documented in the relevant README
- [ ] Experiment scripts produce deterministic, reproducible results
- [ ] License headers are included in new source files

## Reporting Issues

Please use the GitHub Issues tracker. Include:
- Hardware platform (SDR board model, FPGA version)
- Software versions (Linux kernel, Vivado, ROS distro)
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs or error messages

## License

By contributing, you agree that your contributions will be licensed under the AGPL-3.0 license, matching the project license inherited from upstream openwifi.
