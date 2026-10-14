//! `demeter._rs`: the compiled half of the python `demeter` package.
//!
//! The python modules under `rust/python/demeter` keep the original public API
//! (`Actuator`, `Strategy`, `UniLpMarket`, ...) and delegate the heavy work to these classes.

mod conv;
mod engine;
mod market;
mod snapshot;

use pyo3::prelude::*;

#[pymodule]
fn _rs(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<market::PyMarketCore>()?;
    m.add_class::<market::PyDataHandle>()?;
    m.add_class::<engine::PyBrokerCore>()?;
    m.add_class::<engine::PyActuatorCore>()?;
    m.add_class::<snapshot::PySnapshot>()?;
    m.add_class::<snapshot::BarView>()?;
    m.add_class::<snapshot::PriceRow>()?;
    m.add_class::<snapshot::MarketStatusMap>()?;
    m.add_class::<snapshot::NativeTrigger>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
