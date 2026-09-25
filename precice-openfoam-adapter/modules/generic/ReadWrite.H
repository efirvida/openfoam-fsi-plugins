#ifndef MODULE_ReadWrite_H
#define MODULE_ReadWrite_H

#include "Interface.H"
#include "CouplingDataUser.H"

#include "fvCFD.H"
#include "cellSet.H"
#include "uniformDimensionedFields.H"
#include "vectorIOField.H"

#include <memory>

namespace preciceAdapter
{
namespace Generic
{

class ScalarFieldCoupler : public CouplingDataUser // One CouplingDataUser for each field
{
protected:
    Foam::volScalarField* scalarField_;
    const Foam::fvMesh& mesh_;
    const preciceAdapter::FieldConfig& fieldConfig_;

public:
    ScalarFieldCoupler(const Foam::fvMesh& mesh, const preciceAdapter::FieldConfig& fieldConfig);

    void initialize();
    std::size_t write(double* buffer, bool meshConnectivity, const unsigned int dim);
    void read(double* buffer, const unsigned int dim);
    bool isLocationTypeSupported(const bool meshConnectivity) const;
    std::string getDataName() const;

    virtual ~ScalarFieldCoupler() {};
};

class VectorFieldCoupler : public CouplingDataUser
{
protected:
    Foam::volVectorField* vectorField_;
    const Foam::fvMesh& mesh_;
    const preciceAdapter::FieldConfig& fieldConfig_;

public:
    VectorFieldCoupler(const Foam::fvMesh& mesh, const preciceAdapter::FieldConfig& fieldConfig);

    void initialize();
    std::size_t write(double* buffer, bool meshConnectivity, const unsigned int dim);
    void read(double* buffer, const unsigned int dim);
    bool isLocationTypeSupported(const bool meshConnectivity) const;
    std::string getDataName() const;

    virtual ~VectorFieldCoupler() {};
};

class GlobalScalarFieldCoupler : public CouplingDataUser
{
protected:
    const Foam::Time& runTime_;
    const preciceAdapter::FieldConfig& fieldConfig_;
    mutable Foam::uniformDimensionedScalarField* scalarField_ = nullptr;
    mutable std::unique_ptr<Foam::uniformDimensionedScalarField> scalarFieldOwning_;

    void bindField() const;

public:
    GlobalScalarFieldCoupler(const Foam::fvMesh& mesh, const preciceAdapter::FieldConfig& fieldConfig);

    void initialize();
    std::size_t write(double* buffer, bool meshConnectivity, const unsigned int dim);
    void read(double* buffer, const unsigned int dim);
    bool isLocationTypeSupported(const bool meshConnectivity) const;
    std::string getDataName() const;

    virtual ~GlobalScalarFieldCoupler() {};
};

class GlobalVectorFieldCoupler : public CouplingDataUser
{
protected:
    const Foam::Time& runTime_;
    const preciceAdapter::FieldConfig& fieldConfig_;
    mutable Foam::uniformDimensionedVectorField* vectorField_ = nullptr;
    mutable std::unique_ptr<Foam::uniformDimensionedVectorField> vectorFieldOwning_;

    void bindField() const;

public:
    GlobalVectorFieldCoupler(const Foam::fvMesh& mesh, const preciceAdapter::FieldConfig& fieldConfig);

    void initialize();
    std::size_t write(double* buffer, bool meshConnectivity, const unsigned int dim);
    void read(double* buffer, const unsigned int dim);
    bool isLocationTypeSupported(const bool meshConnectivity) const;
    std::string getDataName() const;

    virtual ~GlobalVectorFieldCoupler() {};
};

//- Coupler for a replicated point cloud stored as a registry vectorIOField.
//  The field is owned by the surface sampler (turbinesFoam); this coupler
//  only binds to it by name and exchanges the whole vertex list.
class PointCloudVectorCoupler : public CouplingDataUser
{
protected:
    const Foam::Time& runTime_;
    const preciceAdapter::FieldConfig& fieldConfig_;
    mutable Foam::vectorIOField* vectorField_ = nullptr;

    void bindField() const;

public:
    PointCloudVectorCoupler(const Foam::fvMesh& mesh, const preciceAdapter::FieldConfig& fieldConfig);

    void initialize();
    std::size_t write(double* buffer, bool meshConnectivity, const unsigned int dim);
    void read(double* buffer, const unsigned int dim);
    bool isLocationTypeSupported(const bool meshConnectivity) const;
    std::string getDataName() const;

    virtual ~PointCloudVectorCoupler() {};
};

}
}

#endif
